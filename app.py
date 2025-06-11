# -----------------------------------------------
# 1. 必要なライブラリを準備
# -----------------------------------------------
import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
from google.oauth2 import service_account

# -----------------------------------------------
# 2. ★★★ GCP認証と初期設定 ★★★
# -----------------------------------------------
try:
    # .streamlit/secrets.toml の [gcp] セクションを読み込む
    gcp_cfg = st.secrets["gcp"]
    GCP_PROJECT_ID = gcp_cfg["project_id"]
    GCP_REGION     = "asia-northeast1"

    # JSON文字列を辞書化
    service_account_info = json.loads(gcp_cfg["gcp_service_account"])

    # 認証用オブジェクトを作成
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info
    )

    # Vertex AI 初期化
    vertexai.init(
        project     = GCP_PROJECT_ID,
        location    = GCP_REGION,
        credentials = credentials
    )
    model = GenerativeModel("gemini-1.5-pro")

    GCP_AUTH_SUCCESS = True

except Exception as e:
    GCP_AUTH_SUCCESS = False
    st.error(f"GCPの認証に失敗しました。\nStreamlitのSecrets設定を確認してください。\nエラー: {e}")

# -----------------------------------------------
# 3. UI（画面）部分
# -----------------------------------------------
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

prompt = """
あなたは、日本のリフォーム・原状回復工事を専門とする、経験豊富な積算担当者です。

これから提供する現場写真と図面に基づき、以下の#出力フォーマットと#見積もり作成ルールに厳密に従って、プロフェッショナルな工事見積書を日本語で作成してください。このプロンプトには、理想的な見積書のすべての要素が含まれています。

# プロジェクト概要
工事種別: (例: 中古マンションのフルリノベーション / オフィスの原状回復)
物件名: (例: ○○ビル 301号室)
住所: (例: 東京都渋谷区○○ 1-2-3)
依頼主の要望:
(例: 2LDKを広い1LDKに変更したい)
(例: 内装は白を基調としたシンプルモダンなデザインを希望)
(例: 水回りの設備はすべて一新したい)
(例: 予算は税込みでXXX万円以内を希望)
# 入力データ
現場写真:
[写真1.jpg] - [写真5.jpg]: 各部屋の現状（リビング、和室、キッチン、浴室、トイレ）
[写真6.jpg]: キッチンの配管周りの腐食が確認できるアップ
[写真7.jpg]: 窓サッシの歪みと隙間がわかるアップ
図面:
[平面図.pdf]: 各部屋の寸法、間取り、建具の位置が記載
[電気配線図.pdf]: 既存のスイッチ、コンセント、照明の位置が記載
# 出力フォーマット
以下の構成と項目を厳密に守り、見積書を作成してください。

1. ヘッダー

書類名: 御見積書
見積書番号: No. (6桁の数字で自動生成)
発行日: (今日の日付)
宛名: (指定がない場合は「○○様」)
発行元情報:
会社名: (あなたの会社名)
住所: (あなたの住所)
電話/FAX: (あなたの連絡先)
登録番号: (例: T3010901009251) 111111111


2. 物件情報・条件

物件名: (プロジェクト概要から転記)
住所: (プロジェクト概要から転記)
取引方法: (例: 合意書の通り) 222222222



有効期限: 3ヶ月 333333333



3. 合計金額

合計金額(税込) ¥X,XXX,XXX- の形式で記載 444444444。



その下に (税率10%対象X,XXX,XXX円 消費税XXX,XXX円) の形式で内訳を併記 555
"""

# -----------------------------------------------
# 4. 分析開始ボタン押下時の処理
# -----------------------------------------------
if st.button("分析を開始する"):
    if not GCP_AUTH_SUCCESS:
        st.stop()  # 認証エラーは上部で報告済み

    if not uploaded:
        st.warning("まずはファイルをアップロードしてください。")
        st.stop()

    with st.spinner("AIが写真を分析中です…"):
        try:
            # 画像データを Part オブジェクトに変換
            parts = [
                Part.from_data(data=f.getvalue(), mime_type=f.type)
                for f in uploaded
            ]

            # ここで request_options を外しています
            contents = [prompt] + parts
            response = model.generate_content(contents)

            st.subheader("🔍 分析結果")
            st.markdown(response.text)
            st.success("✅ 分析が完了しました！")

        except Exception as e:
            st.error(f"分析中にエラーが発生しました: {e}")
