import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
from google.oauth2 import service_account
import base64  # ← 追加

# 省略：GCP認証まわりはそのまま

st.title("📷 AIによるリフォーム箇所分析アプリ")
st.markdown("""
360度写真や、気になる箇所の詳細な写真をアップロードしてください。  
AIが写真を分析し、リフォームや修繕が必要な箇所を自動でリストアップします。
""")

uploaded = st.file_uploader(
    "分析したい写真を選択してください（複数選択可）",
    type=["png","jpg","jpeg"],
    accept_multiple_files=True
)

# ───────────────────────────────────────
# アップロード直後にプレビュー＆ファイル名を表示
# ───────────────────────────────────────
if uploaded:
    st.subheader("アップロード画像プレビュー")
    cols = st.columns(3)
    for idx, file in enumerate(uploaded):
        cols[idx % 3].image(
            file,
            caption=file.name,
            width=150
        )

prompt = """（省略：元のプロンプトをここに入れてください）"""

if st.button("分析を開始する"):
    if not uploaded:
        st.warning("まずはファイルをアップロードしてください。")
        st.stop()

    with st.spinner("AIが写真を分析中です…"):
        # モデル呼び出し
        parts = [Part.from_data(data=f.getvalue(), mime_type=f.type) for f in uploaded]
        contents = [prompt] + parts
        response = model.generate_content(contents)

    # ───────────────────────────────────────
    # 1-2節までは元テキストをそのまま描画し、
    # 「3. 写真のサムネイル」以降は自前で表示する
    # ───────────────────────────────────────
    st.subheader("🔍 分析結果")

    lines = response.text.splitlines()

    # 1-2節をそのまま
    for line in lines:
        if line.startswith("3. 写真のサムネイル"):
            break
        st.markdown(line)

    # 独自表示：写真ごとのプレビュー＋コメント
    st.markdown("### 写真ごとのプレビュー＆コメント")

    # まず、モデルの出力から「写真」テーブル行だけを抽出
    table_rows = []
    in_table = False
    for line in lines:
        if line.strip().startswith("| 写真") and "サムネイル" in line:
            in_table = True
            continue
        if in_table:
            if line.strip().startswith("| 写真"):
                cols = [c.strip() for c in line.split("|")[1:-1]]
                # cols = [ "写真1", "サムネイル", "コメント本文" ]
                if len(cols) >= 3:
                    table_rows.append((cols[0], cols[2]))
            else:
                break  # テーブル終了

    # uploaded の順番に対応させて描画
    for idx, file in enumerate(uploaded):
        photo_label, comment = table_rows[idx] if idx < len(table_rows) else (f"写真{idx+1}", "")

        # base64化してクリックで元サイズ表示
        b64 = base64.b64encode(file.getvalue()).decode()
        mime = file.type
        thumb_html = (
            f'<a href="data:{mime};base64,{b64}" target="_blank">'
            f'<img src="data:{mime};base64,{b64}" width="150" style="border:1px solid #ccc;"/>'
            "</a>"
        )

        st.markdown(
            f"**{photo_label}：{file.name}**  \n"
            f"{thumb_html}  \n\n"
            f"{comment}",
            unsafe_allow_html=True
        )

    # ───────────────────────────────────────
    # 必要ならテーブル後の残りのレポートを出力
    # ───────────────────────────────────────
    # （ここでは省略していますが、同様に lines の続きを st.markdown で出せます）

    st.success("✅ 分析が完了しました！")
