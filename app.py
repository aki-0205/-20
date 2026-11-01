import streamlit as st
import json
import os
import base64
import copy
import requests

from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from collections import Counter

# ==========================================
# ナンバーズミニ予測アプリ
# ==========================================

st.set_page_config(
    page_title="ナンバーズミニ予測",
    page_icon="🎯",
    layout="centered"
)

JST = ZoneInfo("Asia/Tokyo")

# GitHub保存設定
GITHUB_REPO = "aki-0205/numbers3-mini-app4"
GITHUB_BRANCH = "main"
DATA_FILE = "mini_history.json"

GITHUB_API_URL = (
    f"https://api.github.com/repos/{GITHUB_REPO}/contents/{DATA_FILE}"
)

START_DATE = date(2026, 10, 29)
MAX_DAILY_RECORDS = 50

DEFAULT_DATA = {
    "history": [],
    "forecast": {},
    "daily_records": []
}


# ==========================================
# GitHub接続設定
# ==========================================

def get_github_headers():
    token = st.secrets.get("GITHUB_TOKEN", "")

    if not token:
        raise RuntimeError(
            "GitHubトークンが設定されていません。"
            "StreamlitのSecretsにGITHUB_TOKENを設定してください。"
        )

    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }


# ==========================================
# GitHubからデータ読み込み
# ==========================================

def load_data():
    headers = get_github_headers()

    response = requests.get(
        GITHUB_API_URL,
        headers=headers,
        params={"ref": GITHUB_BRANCH},
        timeout=20
    )

    # データファイルがまだ存在しない場合
    if response.status_code == 404:
        return copy.deepcopy(DEFAULT_DATA)

    if response.status_code != 200:
        raise RuntimeError(
            f"GitHubからの読み込みに失敗しました。"
            f"HTTP {response.status_code}: {response.text}"
        )

    try:
        file_info = response.json()

        content = base64.b64decode(
            file_info["content"]
        ).decode("utf-8")

        data = json.loads(content)

        if not isinstance(data, dict):
            raise ValueError("データ形式が正しくありません。")

        data.setdefault("history", [])
        data.setdefault("forecast", {})
        data.setdefault("daily_records", [])

        return data

    except Exception as e:
        raise RuntimeError(
            f"保存データの読み込みに失敗しました: {e}"
        )


# ==========================================
# GitHubへデータ保存
# ==========================================

def save_data():
    headers = get_github_headers()

    # 現在のGitHubファイル情報を取得
    response = requests.get(
        GITHUB_API_URL,
        headers=headers,
        params={"ref": GITHUB_BRANCH},
        timeout=20
    )

    sha = None

    if response.status_code == 200:
        sha = response.json().get("sha")

    elif response.status_code != 404:
        raise RuntimeError(
            f"GitHubの保存データ確認に失敗しました。"
            f"HTTP {response.status_code}: {response.text}"
        )

    # JSONデータをBase64に変換
    json_text = json.dumps(
        st.session_state.data,
        ensure_ascii=False,
        indent=2
    )

    encoded_content = base64.b64encode(
        json_text.encode("utf-8")
    ).decode("utf-8")

    payload = {
        "message": "Update Numbers Mini data",
        "content": encoded_content,
        "branch": GITHUB_BRANCH
    }

    # 既存ファイルならSHAを指定して更新
    if sha:
        payload["sha"] = sha

    response = requests.put(
        GITHUB_API_URL,
        headers=headers,
        json=payload,
        timeout=30
    )

    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"GitHubへの保存に失敗しました。"
            f"HTTP {response.status_code}: {response.text}"
        )

    return True


# ==========================================
# 数字のチェック
# ==========================================

def valid_number(value):
    value = str(value).strip()

    if not value.isdigit():
        return None

    number = int(value)

    if 0 <= number <= 99:
        return f"{number:02d}"

    return None


# ==========================================
# 予測計算
# ==========================================

def make_predictions(history):
    """
    既存の複合スコア方式を維持する。
    過去50回を使って20数字を選ぶ。
    """

    recent = history[-50:]
    recent20 = history[-20:]
    recent10 = history[-10:]

    c50 = Counter(recent)
    c20 = Counter(recent20)
    c10 = Counter(recent10)

    tens = Counter(int(n[0]) for n in recent)
    ones = Counter(int(n[1]) for n in recent)

    last_seen = {
        number: i for i, number in enumerate(history)
    }

    scores = {}

    for i in range(100):
        n = f"{i:02d}"

        if n in last_seen:
            gap = len(history) - 1 - last_seen[n]
        else:
            gap = 50

        scores[n] = (
            c50[n]
            + 1.5 * c20[n]
            + 2.0 * c10[n]
            + 0.10 * min(gap, 20)
            + 0.15 * tens[i // 10]
            + 0.15 * ones[i % 10]
        )

    ranked = sorted(
        scores.keys(),
        key=lambda n: (-scores[n], n)
    )

    return ranked[:20]


# ==========================================
# 予測対象日
# ==========================================

def get_target_date(now):
    """
    朝8時より前：前日の予測を表示
    朝8時以降：当日の予測を表示
    """

    if now.time() >= time(8, 0):
        return now.date()

    return now.date() - timedelta(days=1)


# ==========================================
# 抽選日の記録取得
# ==========================================

def get_daily_record(records, draw_date):
    key = draw_date.isoformat()

    for record in records:
        if record.get("date") == key:
            return record

    return None


# ==========================================
# 予測作成・固定
# ==========================================

def ensure_forecast():
    """
    対象日ごとに予測を1回だけ作成する。

    ・朝8時に対象日が切り替わる
    ・作成済みの20数字は同じ対象日の間、変更しない
    ・当日の当選数字を入力しても、作成済み予測は変更しない
    ・前日の当選数字が未登録なら、新しい予測を作成しない
    """

    now = datetime.now(JST)
    target = get_target_date(now)
    key = target.isoformat()

    data = st.session_state.data
    forecasts = data["forecast"]

    # 作成済みの予測があれば、その20数字をそのまま使う
    if key in forecasts:
        return forecasts[key], target

    history = data["history"]

    # 予測用の履歴がなければ作成できない
    if len(history) == 0:
        return None, target

    # 初回対象日より後は、前日の当選数字が必要
    if target > START_DATE:
        previous_date = target - timedelta(days=1)

        previous_record = get_daily_record(
            data["daily_records"],
            previous_date
        )

        if previous_record is None:
            return None, target

    # 対象日の予測を初めて作成
    numbers = make_predictions(history)

    forecasts[key] = {
        "numbers": numbers,
        "created_at": now.isoformat(),
        "history_count": len(history)
    }

    try:
        save_data()

    except Exception as e:
        del forecasts[key]
        st.error(f"予測の保存に失敗しました: {e}")
        return None, target

    return forecasts[key], target


# ==========================================
# 当選数字の保存・修正
# ==========================================

def save_daily_result(draw_date, winning):
    """
    抽選日ごとの当選数字を保存する。

    ・当日の予測がなくても当選数字を保存できる
    ・新規登録時は予測計算用履歴にも追加する
    ・同じ日付の修正では履歴内の対応数字を更新する
    ・GitHubへの保存に成功した場合だけ確定する
    """

    data = st.session_state.data

    # 保存失敗時に元へ戻せるようにバックアップ
    backup = copy.deepcopy(data)

    key = draw_date.isoformat()
    records = data["daily_records"]

    existing_index = next(
        (
            i for i, item in enumerate(records)
            if item.get("date") == key
        ),
        None
    )

    forecast = data["forecast"].get(key)

    # 予測がない場合は空の予測として記録
    predicted = (
        forecast.get("numbers", [])
        if forecast
        else []
    )

    if existing_index is None:

        # 履歴が50回に達している場合、
        # 古い履歴を削除する前に記録位置を調整
        if len(data["history"]) >= 50:

            for item in records:
                history_index = item.get("history_index")

                if isinstance(history_index, int):
                    if history_index == 0:
                        item["history_index"] = None
                    else:
                        item["history_index"] = history_index - 1

        # 新しい当選数字を履歴に追加
        data["history"].append(winning)
        data["history"] = data["history"][-50:]

        record = {
            "date": key,
            "winning": winning,
            "predicted": predicted,
            "history_index": len(data["history"]) - 1,
            "forecast_created_at": (
                forecast.get("created_at", "")
                if forecast
                else ""
            ),
            "updated_at": datetime.now(JST).isoformat()
        }

        records.append(record)

    else:

        record = records[existing_index]
        old_winning = record.get("winning")

        # 当選数字を修正した場合、履歴も修正
        if old_winning != winning:

            record["winning"] = winning

            history_index = record.get("history_index")

            if (
                isinstance(history_index, int)
                and 0 <= history_index < len(data["history"])
            ):
                data["history"][history_index] = winning

        record["predicted"] = predicted
        record["updated_at"] = datetime.now(JST).isoformat()

    records.sort(
        key=lambda item: item.get("date", "")
    )

    # 2026年10月29日より前を除き、最新50回分を保持
    records = [
        item for item in records
        if item.get("date", "") >= START_DATE.isoformat()
    ]

    data["daily_records"] = records[-MAX_DAILY_RECORDS:]

    # GitHubに保存
    try:
        save_data()
        return True, "当選数字をGitHubに保存しました。"

    except Exception as e:
        # 保存失敗なら変更前のデータに戻す
        st.session_state.data = backup

        return False, f"GitHubへの保存に失敗しました: {e}"


# ==========================================
# バックテスト
# ==========================================

def backtest(history):
    """
    既存のバックテスト方式を維持する。
    """

    results = []

    for i in range(50, len(history)):
        previous = history[i - 50:i]
        actual = history[i]
        predicted = make_predictions(previous)

        results.append({
            "回": i + 1,
            "当選数字": actual,
            "的中": actual in predicted
        })

    return results


# ==========================================
# 累積的中率
# ==========================================

def calculate_daily_results(records):
    """
    抽選日順に累積的中率を計算する。

    予測が保存されていない日は、
    的中率の計算対象から除外する。
    """

    results = []
    hits = 0
    count = 0

    sorted_records = sorted(
        records,
        key=lambda item: item.get("date", "")
    )

    for record in sorted_records:

        winning = record.get("winning")
        predicted = record.get("predicted", [])

        # 予測が存在しない日は対象外
        if not winning or not predicted:
            continue

        count += 1
        hit = winning in predicted

        if hit:
            hits += 1

        results.append({
            "date": record.get("date", ""),
            "winning": winning,
            "hit": hit,
            "hits": hits,
            "count": count,
            "rate": hits / count * 100
        })

    return results


# ==========================================
# GitHubからデータ読み込み
# ==========================================

if "data" not in st.session_state:

    try:
        st.session_state.data = load_data()

    except Exception as e:
        st.error(f"データを読み込めませんでした: {e}")
        st.stop()


data = st.session_state.data


# ==========================================
# タイトル
# ==========================================

st.title("🎯 ナンバーズミニ予測")

st.caption(
    "20口予測・朝8時切り替え・抽選結果50回管理"
)

now = datetime.now(JST)
target = get_target_date(now)

st.write(
    f"現在時刻：{now.strftime('%Y/%m/%d %H:%M:%S')}"
)

st.write(
    f"予測対象日：{target.strftime('%Y年%m月%d日')}"
)

st.divider()


# ==========================================
# 予測表示
# ==========================================

st.subheader("予測数字20口")

forecast, target = ensure_forecast()

if forecast is None:

    previous_date = target - timedelta(days=1)

    previous_record = get_daily_record(
        data["daily_records"],
        previous_date
    )

    if target > START_DATE and previous_record is None:

        st.warning(
            f"{previous_date.strftime('%Y年%m月%d日')}の当選数字が未登録です。"
            "当選数字を登録すると、その結果を反映した当日の予測20個を作成します。"
        )

    else:

        st.warning(
            "予測用の履歴がありません。"
            "予測を作るには、予測計算用の履歴が必要です。"
        )

else:

    numbers = forecast["numbers"]

    st.caption(
        "この予測は対象日の間、固定されます。"
    )

    st.write(
        f"作成日時：{forecast['created_at']}"
    )

    st.write(
        f"計算に使った履歴：{forecast['history_count']}回分"
    )

    for i in range(0, 20, 5):

        st.write(
            f"{i + 1:02d}〜{i + 5:02d}口"
        )

        st.markdown(
            "**" + "　".join(numbers[i:i + 5]) + "**"
        )


# ==========================================
# 抽選日ごとの当選数字入力
# ==========================================

st.divider()

st.subheader("抽選日ごとの当選数字入力")

st.write(
    "2026年10月29日を1回目として、抽選日ごとに当選数字を保存します。"
)

st.write(
    "前日の当選数字は、翌日の朝8時までに入力してください。"
)

st.write(
    "同じ抽選日を再入力すると、その日の当選数字を修正できます。"
)

now_for_entry = datetime.now(JST)
today_jst = now_for_entry.date()

# 朝8時前は前日の結果を入力しやすいように前日を初期表示
default_draw_date = get_target_date(now_for_entry)

# 朝8時以降でも前日の結果が未登録なら前日を初期表示
if now_for_entry.time() >= time(8, 0):

    previous_date = today_jst - timedelta(days=1)

    if today_jst > START_DATE:

        previous_record = get_daily_record(
            data["daily_records"],
            previous_date
        )

        if previous_record is None:
            default_draw_date = previous_date

default_draw_date = max(
    START_DATE,
    default_draw_date
)


with st.form(
    "dated_result_entry",
    clear_on_submit=False
):

    draw_date = st.date_input(
        "抽選日",
        value=default_draw_date,
        min_value=START_DATE,
        format="YYYY/MM/DD"
    )

    existing_record = get_daily_record(
        data["daily_records"],
        draw_date
    )

    current_winning = (
        existing_record.get("winning", "")
        if existing_record
        else ""
    )

    winning_input = st.text_input(
        "当選数字（00〜99）",
        value=current_winning,
        max_chars=2,
        placeholder="例：25"
    )

    submitted_dated = st.form_submit_button(
        "当選数字を保存・更新",
        use_container_width=True
    )


if submitted_dated:

    winning = valid_number(winning_input)

    if winning is None:

        st.error(
            "00〜99の数字を入力してください。"
        )

    else:

        success, message = save_daily_result(
            draw_date,
            winning
        )

        if success:
            st.success(message)

        else:
            st.error(message)


# ==========================================
# 抽選結果・当選確率の履歴（最大50回）
# ==========================================

st.divider()

st.subheader(
    "抽選結果・当選確率の履歴（最大50回）"
)

daily_results = calculate_daily_results(
    data["daily_records"]
)

if not daily_results:

    st.info(
        "予測が保存されている抽選日の当選数字を入力すると、"
        "ここに抽選日・当選数字・累積的中率が表示されます。"
    )

else:

    latest = daily_results[-1]

    st.metric(
        "入力済み抽選の累積的中率",
        f"{latest['rate']:.1f}%"
    )

    st.write(
        f"的中：{latest['hits']}回 / "
        f"当選数字入力済み：{latest['count']}回"
    )

    for index, result in enumerate(
        daily_results,
        start=1
    ):

        draw_date = date.fromisoformat(
            result["date"]
        )

        hit_label = (
            "的中" if result["hit"] else "外れ"
        )

        with st.container(border=True):

            st.write(
                f"{index}回目　"
                f"{draw_date.strftime('%Y年%m月%d日')}"
            )

            st.write(
                f"抽選数字：**{result['winning']}**"
            )

            st.write(
                f"当選確率：**{result['rate']:.1f}%**"
            )

            st.caption(
                f"累積 {result['count']}回中 "
                f"{result['hits']}回的中"
                f"（今回：{hit_label}）"
            )

    st.caption(
        "表示順は抽選日の古い順です。51回目の記録が加わると、"
        "最も古い記録が表示対象から外れます。"
    )


# ==========================================
# 過去データでの検証（既存機能）
# ==========================================

st.divider()

st.subheader("過去データでの検証")

results = backtest(data["history"])

if not results:

    st.info(
        "公平なバックテストには、直前50回と検証対象の当選数字が必要です。"
        "最低51回分の履歴が必要です。"
    )

else:

    hits = sum(
        r["的中"] for r in results
    )

    total = len(results)
    rate = hits / total * 100

    st.metric(
        "バックテスト的中率",
        f"{rate:.1f}%"
    )

    st.write(
        f"的中：{hits}回 / 検証回数：{total}回"
    )

    st.caption(
        "これは過去の検証結果であり、将来の当選確率ではありません。"
    )

    with st.expander("検証結果一覧"):

        st.dataframe(
            [
                {
                    "履歴位置": r["回"],
                    "当選数字": r["当選数字"],
                    "結果": (
                        "的中" if r["的中"] else "外れ"
                    )
                }
                for r in results
            ],
            use_container_width=True,
            hide_index=True
        )


# ==========================================
# 現在の履歴
# ==========================================

st.divider()

st.subheader("現在の履歴")

st.write(
    f"保存されている履歴：{len(data['history'])}回分"
)

with st.expander("履歴を表示"):

    st.write(
        " → ".join(data["history"])
    )

st.caption(
    "当選数字と予測データはGitHubに保存されます。"
)
