import streamlit as st
import pandas as pd
from collections import Counter
from datetime import date
import json, os

st.set_page_config(
    page_title="ナンバーズミニ20口比較",
    page_icon="🎯",
    layout="centered"
)

INITIAL_50_NEWEST_FIRST = [
    "16", "45", "25", "86", "08", "11", "45", "15", "52", "10",
    "31", "75", "45", "05", "69", "69", "06", "18", "20", "02",
    "26", "39", "87", "56", "82", "66", "88", "29", "53", "88",
    "08", "60", "50", "94", "82", "51", "66", "12", "82", "77",
    "91", "60", "08", "86", "37", "86", "19", "72", "09", "78"
]

# 初期データを古い順に並べる仮定
INITIAL_50 = list(reversed(INITIAL_50_NEWEST_FIRST))
DATA_FILE = "mini_history.json"


def normalize(v):
    s = str(v).strip()
    if not s.isdigit() or not 0 <= int(s) <= 99:
        return None
    return f"{int(s):02d}"


def load_history():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                vals = [normalize(x) for x in raw]
                vals = [x for x in vals if x is not None]
                if vals:
                    return vals
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return INITIAL_50.copy()


def save_history(hist):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def original_prediction(hist):
    """元コードの意図を再現した予測方式"""
    counts = Counter(hist)
    odd = sum(int(x) % 2 for x in hist)
    even = len(hist) - odd
    scores = {}

    for i in range(100):
        n = f"{i:02d}"
        score = counts[n] * 10.0

        if n in hist[-10:]:
            score += 3.0

        if n in hist[-5:]:
            score += 2.0

        if odd > even + 5 and i % 2 == 0:
            score += 1.5
        elif even > odd + 5 and i % 2 == 1:
            score += 1.5

        scores[n] = score

    excluded = (
        {f"{i}{i}" for i in range(10)}
        if hist and hist[-1][0] == hist[-1][1]
        else set()
    )

    return [
        n for n in sorted(
            scores,
            key=lambda x: (-scores[x], x)
        )
        if n not in excluded
    ][:20]


def composite_prediction(hist):
    """独自の複合方式。優位性が実証された方式ではありません。"""
    h50 = hist[-50:]
    h20 = hist[-20:]
    h10 = hist[-10:]

    c50 = Counter(h50)
    c20 = Counter(h20)
    c10 = Counter(h10)

    tens = Counter(int(x[0]) for x in h50)
    ones = Counter(int(x[1]) for x in h50)

    last_seen = {v: i for i, v in enumerate(hist)}
    scores = {}

    for i in range(100):
        n = f"{i:02d}"

        gap = (
            len(hist) - 1 - last_seen[n]
            if n in last_seen
            else min(len(hist), 50)
        )

        scores[n] = (
            c50[n]
            + 1.5 * c20[n]
            + 2 * c10[n]
            + 0.10 * min(gap, 20)
            + 0.15 * tens[i // 10]
            + 0.15 * ones[i % 10]
        )

    return sorted(
        scores,
        key=lambda x: (-scores[x], x)
    )[:20]


def predict(hist, method):
    if method == "元の方式":
        return original_prediction(hist)
    return composite_prediction(hist)


def backtest(hist, method, window=50):
    """各回より前の履歴だけを使って検証する"""
    rows = []

    for i in range(window, len(hist)):
        predicted = predict(hist[i - window:i], method)
        actual = hist[i]

        rows.append({
            "履歴位置": i + 1,
            "当選数字": actual,
            "的中": actual in predicted
        })

    return rows


if "history" not in st.session_state:
    st.session_state.history = load_history()

hist = st.session_state.history

st.markdown("## 🎯 ナンバーズミニ 20口予測・比較")
st.caption(f"履歴：{len(hist)}回（古い順→新しい順）")

method = st.radio(
    "予測方式",
    ["元の方式", "独自の複合方式"],
    horizontal=True
)

nums = predict(hist, method)

st.subheader(f"{method}の予測20口")

for i in range(0, 20, 5):
    st.write(
        f"口{i+1:02d}〜{i+5:02d}：　"
        + "　".join(nums[i:i+5])
    )

st.markdown("**" + "　".join(nums) + "**")
st.caption("予測は参考情報です。当選を保証するものではありません。")

st.divider()
st.subheader("過去データでの公平なバックテスト")

st.write(
    "各回の抽選前に存在した直近50回だけで20口を作り、"
    "その回の当選数字が含まれたかを検証します。"
)

a = backtest(hist, "元の方式")
b = backtest(hist, "独自の複合方式")

if len(hist) < 100:
    st.warning(
        f"履歴は{len(hist)}回です。"
        f"直前50回を使う検証は{len(a)}回分です。"
        "50回分の検証結果を得るには最低100回分の履歴が必要です。"
    )

if a:
    ah = sum(r["的中"] for r in a)
    bh = sum(r["的中"] for r in b)
    total = len(a)

    c1, c2 = st.columns(2)

    c1.metric(
        "元の方式",
        f"{ah}/{total}",
        f"{ah/total*100:.1f}%"
    )

    c2.metric(
        "独自の複合方式",
        f"{bh}/{total}",
        f"{bh/total*100:.1f}%"
    )

    st.dataframe(
        pd.DataFrame([
            {
                "方式": "元の方式",
                "的中数": ah,
                "検証回数": total,
                "的中率(%)": round(ah / total * 100, 1)
            },
            {
                "方式": "独自の複合方式",
                "的中数": bh,
                "検証回数": total,
                "的中率(%)": round(bh / total * 100, 1)
            }
        ]),
        hide_index=True,
        use_container_width=True
    )

    with st.expander("各回の検証結果"):
        st.dataframe(
            pd.DataFrame({
                "履歴位置": [r["履歴位置"] for r in a],
                "当選数字": [r["当選数字"] for r in a],
                "元の方式": [
                    "的中" if r["的中"] else "外れ" for r in a
                ],
                "独自方式": [
                    "的中" if r["的中"] else "外れ" for r in b
                ]
            }),
            hide_index=True,
            use_container_width=True
        )
else:
    st.info(
        "まだ厳密なバックテスト結果はありません。"
        "履歴が51回以上になると検証を開始し、"
        "100回あれば50回分を検証できます。"
    )

st.divider()
st.subheader("当選数字の登録")

with st.form("add_draw", clear_on_submit=True):
    d = st.date_input("抽選日", value=date.today(), max_value=date.today())
    win = st.text_input("当選数字（2桁、例：03）", max_chars=2)
    submitted = st.form_submit_button("登録")

if submitted:
    n = normalize(win)

    if n is None or len(win.strip()) != 2:
        st.error("00〜99の数字を2桁で入力してください。")
    else:
        st.session_state.history.append(n)

        if save_history(st.session_state.history):
            st.success(
                f"{d.strftime('%Y/%m/%d')} の当選数字 {n} を登録しました。"
            )
        else:
            st.error("履歴を保存できませんでした。")

        st.rerun()

st.divider()
st.subheader("履歴の管理")

st.caption(
    "古い当選数字から新しい当選数字の順に入力してください。"
    "1行に1個、またはカンマ区切りです。"
)

with st.expander("履歴をまとめて編集・バックアップ"):
    txt = st.text_area(
        "履歴",
        value="\n".join(hist),
        height=180
    )

    if st.button("編集した履歴を保存"):
        tokens = (
            txt.replace(",", "\n")
            .replace(" ", "\n")
            .splitlines()
        )

        cleaned = []
        invalid = []

        for t in tokens:
            if not t.strip():
                continue

            n = normalize(t)

            if n is None:
                invalid.append(t)
            else:
                cleaned.append(n)

        if invalid:
            st.error("無効な値があります：" + ", ".join(invalid[:10]))
        elif not cleaned:
            st.error("履歴が空です。")
        else:
            st.session_state.history = cleaned

            if save_history(cleaned):
                st.success(f"{len(cleaned)}回分を保存しました。")
            else:
                st.error("履歴を保存できませんでした。")

            st.rerun()

    st.download_button(
        "履歴をJSONで保存",
        data=json.dumps(hist, ensure_ascii=False, indent=2),
        file_name="mini_history_backup.json",
        mime="application/json"
    )

with st.expander("現在の履歴一覧"):
    st.write(" → ".join(hist))

st.caption(
    "バックテストは未来の当選を保証しません。"
    "独自方式が元の方式より優れるかは、"
    "同じデータで検証して判断します。"
)
