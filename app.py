import streamlit as st
import json
import os
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
DATA_FILE = "mini_history.json"
START_DATE = date(2026, 10, 29)
MAX_DAILY_RECORDS = 50

DEFAULT_DATA = {
    "history": [],
    "forecast": {},
    "daily_records": []
}


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict):
                data.setdefault("history", [])
                data.setdefault("forecast", {})
                data.setdefault("daily_records", [])
                return data
        except (OSError, json.JSONDecodeError):
            pass

    return {
        "history": [],
        "forecast": {},
        "daily_records": []
    }


def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(
                st.session_state.data,
                f,
                ensure_ascii=False,
                indent=2
            )
        return True
    except OSError:
        return False


def valid_number(value):
    value = str(value).strip()

    if not value.isdigit():
        return None

    number = int(value)

    if 0 <= number <= 99:
        return f"{number:02d}"

    return None


def make_predictions(history):
    """
    既存の予測方式を維持する。
    過去50回を使う複合スコア方式。
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


def get_target_date(now):
    """
    20時より前：当日向け予測
    20時以降：翌日向け予測
    """
    if now.time() >= time(20, 0):
        return now.date() + timedelta(days=1)

    return now.date()


def ensure_forecast():
    """
    対象日ごとに予測を1回だけ作成する。
    同じ対象日の間は保存済みの20口を使う。
    """
    now = datetime.now(JST)
    target = get_target_date(now)
    key = target.isoformat()

    forecasts = st.session_state.data["forecast"]

    if key not in forecasts:
        history = st.session_state.data["history"]

        if len(history) == 0:
            return None, target

        numbers = make_predictions(history)

        forecasts[key] = {
            "numbers": numbers,
            "created_at": now.isoformat(),
            "history_count": len(history)
        }

        save_data()

    return forecasts[key], target


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
# 抽選日ごとの結果と確率を管理
# ==========================================

def get_daily_record(records, draw_date):
    key = draw_date.isoformat()

    for record in records:
        if record.get("date") == key:
            return record

    return None


def save_daily_result(draw_date, winning):
    """
    日付ごとに当選数字を保存する。
    同じ日付を再入力した場合は上書きする。
    当日の予測20口も一緒に記録する。
    """
    data = st.session_state.data
    key = draw_date.isoformat()

    forecast = data["forecast"].get(key)

    if forecast is None:
        return False, (
            "この抽選日の予測数字が保存されていません。"
            "予測数字が作成された日付を確認してください。"
        )

    predicted = forecast.get("numbers", [])

    record = {
        "date": key,
        "winning": winning,
        "predicted": predicted,
        "forecast_created_at": forecast.get("created_at", ""),
        "updated_at": datetime.now(JST).isoformat()
    }

    records = data["daily_records"]

    existing_index = next(
        (
            i for i, item in enumerate(records)
            if item.get("date") == key
        ),
        None
    )

    if existing_index is None:
        records.append(record)
    else:
        records[existing_index] = record

    records.sort(key=lambda item: item.get("date", ""))

    # 開始日より前のデータを除外し、最新50日分を保持
    records = [
        item for item in records
        if item.get("date", "") >= START_DATE.isoformat()
    ]

    data["daily_records"] = records[-MAX_DAILY_RECORDS:]

    if save_data():
        return True, "当選数字を保存しました。"
    else:
        return False, "保存に失敗しました。"


def calculate_daily_results(records):
    """
    日付順に、当選数字が保存済み予測20口に
    含まれていた割合を累積計算する。

    例：
    1回中1回的中 = 100%
    2回中1回的中 = 50%
    3回中1回的中 = 33.3%
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

        if not winning:
            continue

        count += 1
        hit = winning in predicted

        if hit:
            hits += 1

        rate = hits / count * 100

        results.append({
            "date": record.get("date", ""),
            "winning": winning,
            "hit": hit,
            "hits": hits,
            "count": count,
            "rate": rate
        })

    return results


# ==========================================
# データ初期化
# ==========================================

if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data
history = data["history"]

st.title("🎯 ナンバーズミニ予測")
st.caption("20口予測・20時切り替え・履歴50回管理")

now = datetime.now(JST)
target = get_target_date(now)

st.write(f"現在時刻：{now.strftime('%Y/%m/%d %H:%M:%S')}")
st.write(f"予測対象日：{target.strftime('%Y年%m月%d日')}")

st.divider()

# ==========================================
# 予測表示
# ==========================================

st.subheader("予測数字20口")

forecast, target = ensure_forecast()

if forecast is None:
    st.warning(
        "予測用の履歴がありません。"
        "下の「履歴をまとめて登録」から当選数字を入力してください。"
    )
else:
    numbers = forecast["numbers"]

    st.caption("この予測は次の20時まで固定されます。")

    st.write(f"作成日時：{forecast['created_at']}")
    st.write(f"計算に使った履歴：{forecast['history_count']}回分")

    for i in range(0, 20, 5):
        st.write(f"{i + 1:02d}〜{i + 5:02d}口")
        st.markdown("**" + "　".join(numbers[i:i + 5]) + "**")

    st.divider()

    st.subheader("当選確率")

    st.metric(
        "理論上の的中確率",
        "20%",
        help="00〜99の100通りから異なる20数字を選ぶ場合"
    )

    st.caption(
        "公平な抽選で20口がすべて異なる数字の場合の理論値です。"
        "予測方式によって20%を超えると保証されるものではありません。"
    )

# ==========================================
# 新機能：抽選日ごとの当選数字入力
# ==========================================

st.divider()
st.subheader("抽選日ごとの当選数字入力")

st.write(
    "2026年10月29日を1回目として、抽選日ごとに当選数字を保存します。"
)
st.write(
    "いつでも入力・修正できます。同じ抽選日を再入力すると、"
    "その日の当選数字を上書きして確率を再計算します。"
)

default_draw_date = max(START_DATE, min(date.today(), date.today()))

with st.form("dated_result_entry", clear_on_submit=False):
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
        existing_record["winning"]
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

    if draw_date < START_DATE:
        st.error("抽選日は2026年10月29日以降を指定してください。")
    elif winning is None:
        st.error("00〜99の数字を入力してください。")
    else:
        success, message = save_daily_result(draw_date, winning)

        if success:
            st.success(message)
        else:
            st.error(message)

        st.rerun()

# ==========================================
# 新機能：最大50回分の抽選日・結果・確率表示
# ==========================================

st.divider()
st.subheader("抽選結果・当選確率の履歴（最大50回）")

daily_results = calculate_daily_results(data["daily_records"])

if not daily_results:
    st.info(
        "2026年10月29日以降の当選数字を入力すると、"
        "ここに抽選日・当選数字・累積的中率が表示されます。"
    )
else:
    latest = daily_results[-1]

    st.metric(
        "入力済み抽選の累積的中率",
        f"{latest['rate']:.1f}%",
        help="入力済みの抽選のうち、保存済み予測20口に当選数字が含まれた割合"
    )

    st.write(
        f"的中：{latest['hits']}回 / "
        f"当選数字入力済み：{latest['count']}回"
    )

    for index, result in enumerate(daily_results, start=1):
        draw_date = date.fromisoformat(result["date"])
        hit_label = "的中" if result["hit"] else "外れ"

        with st.container(border=True):
            st.write(
                f"{index}回目　{draw_date.strftime('%Y年%m月%d日')}"
            )

            st.write(f"抽選数字：**{result['winning']}**")

            st.write(
                f"当選確率：**{result['rate']:.1f}%**"
            )

            st.caption(
                f"累積 {result['count']}回中 "
                f"{result['hits']}回的中（今回：{hit_label}）"
            )

    st.caption(
        "表示順は抽選日の古い順です。51回目の記録が加わると、"
        "最も古い記録が表示対象から外れます。"
    )

# ==========================================
# 従来機能：履歴のまとめて登録
# ==========================================

st.divider()
st.subheader("履歴をまとめて登録")

st.write("古い当選数字から新しい当選数字の順に入力してください。")
st.write(
    "1行に1つの数字を入力します。例：\n"
    "16\n45\n25"
)

bulk_text = st.text_area(
    "当選数字一覧",
    height=180,
    placeholder="古い回から順に入力\n例：\n16\n45\n25"
)

replace_history = st.checkbox(
    "現在の履歴を置き換える",
    value=False
)

if st.button("履歴を登録・更新", use_container_width=True):
    tokens = [
        x.strip()
        for x in bulk_text.replace(",", "\n").splitlines()
        if x.strip()
    ]

    cleaned = []
    invalid = []

    for token in tokens:
        n = valid_number(token)

        if n is None:
            invalid.append(token)
        else:
            cleaned.append(n)

    if invalid:
        st.error("入力に不正な値があります：" + ", ".join(invalid))
    elif not cleaned:
        st.error("当選数字を入力してください。")
    else:
        if replace_history:
            data["history"] = cleaned
        else:
            data["history"].extend(cleaned)

        data["history"] = data["history"][-50:]

        # 既存の予測は削除しない
        save_data()

        st.success(
            f"履歴を登録しました。現在の履歴は"
            f"{len(data['history'])}回分です。"
        )

        st.rerun()

# ==========================================
# 従来機能：当選数字を1回分追加
# ==========================================

st.divider()
st.subheader("当選数字を1回分追加")

with st.form("single_entry", clear_on_submit=True):
    draw_number = st.number_input(
        "抽選回番号（任意）",
        min_value=1,
        value=7101,
        step=1
    )

    winning = st.text_input(
        "当選数字（00〜99）",
        max_chars=2,
        placeholder="例：25"
    )

    submitted = st.form_submit_button(
        "当選数字を追加",
        use_container_width=True
    )

if submitted:
    n = valid_number(winning)

    if n is None:
        st.error("00〜99の数字を入力してください。")
    else:
        data["history"].append(n)
        data["history"] = data["history"][-50:]

        if save_data():
            st.success(
                f"第{int(draw_number)}回の当選数字 {n} を追加しました。"
            )
        else:
            st.error("保存に失敗しました。")

        st.rerun()

# ==========================================
# 従来機能：バックテスト
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
    hits = sum(r["的中"] for r in results)
    total = len(results)
    rate = hits / total * 100

    st.metric("バックテスト的中率", f"{rate:.1f}%")
    st.write(f"的中：{hits}回 / 検証回数：{total}回")

    st.caption(
        "これは過去の検証結果であり、将来の当選確率ではありません。"
    )

    with st.expander("検証結果一覧"):
        st.dataframe(
            [
                {
                    "履歴位置": r["回"],
                    "当選数字": r["当選数字"],
                    "結果": "的中" if r["的中"] else "外れ"
                }
                for r in results
            ],
            use_container_width=True,
            hide_index=True
        )

# ==========================================
# 従来機能：現在の履歴
# ==========================================

st.divider()
st.subheader("現在の履歴")

st.write(f"保存されている履歴：{len(data['history'])}回分")

with st.expander("履歴を表示"):
    st.write(" → ".join(data["history"]))

st.caption(
    "注意：Streamlit Community Cloudのローカルファイルは、"
    "再起動・再デプロイなどで消える可能性があります。"
    "長期保存には外部データベースなどの利用を推奨します。"
)
