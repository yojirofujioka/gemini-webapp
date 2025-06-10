# -----------------------------------------------
# 1. 必要なライブラリを準備
# -----------------------------------------------
import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import os
import io # ファイルをメモリ上で扱うために追加
import base64 # データをエンコードするために追加

# -----------------------------------------------
# 2. ★★★ GCP認証と初期設定 ★★★
# -----------------------------------------------
# StreamlitのSecrets機能を使って、安全に認証情報を管理します。
# この情報は後ほどStreamlit Community Cloudに設定します。
try:
    GCP_PROJECT_ID = st.secrets["gcp"]["project_id"]
    GCP_REGION = "asia-northeast1" # 東京リージョン
    
    # SecretsからサービスアカウントのJSON情報を取得
    service_account_info = st.secrets["gcp_service_account"]

    # Vertex AIを初期化
    vertexai.init(project=GCP_PROJECT_ID, location=GCP_REGION, credentials=service_account_info)
    
    # Geminiモデルを準備
    model = GenerativeModel("gemini-1.5-pro-latest")
    
    # 認証成功フラグ
    GCP_AUTH_SUCCESS = True

except Exception as e:
    # 認証失敗した場合
    GCP_AUTH_SUCCESS = False
    # Streamlitの画面にエラーを表示
    st.error(f"GCPの認証に失敗しました。StreamlitのSecrets設定を確認してください。エラー: {e}")


# -----------------------------------------------
# 3. StreamlitアプリのUI（画面）を作成
# -----------------------------------------------
st.title("📷 AIによるリフォーム箇所分析アプリ")

st.markdown("""
360度写真や、気になる箇所の詳細な写真をアップロードしてください。
AIが写真を分析し、リフォームや修繕が必要な箇所を自動でリストアップします。
""")

# (A) ファイルアップロード機能
# `accept_multiple_files=True`で複数ファイルのアップロードを許可
uploaded_files = st.file_uploader(
    "分析したい写真を選択してください（複数選択可）",
    type=['png', 'jpg', 'jpeg'],
    accept_multiple_files=True
)

# (B) AIへの指示内容（プロンプト）
prompt = """
提供された全ての写真について、これは何の画像かを特定し、リフォームや修繕が必要な箇所があれば指摘してください。
特に以下の点に注目してください。

- 360度写真: 全体の雰囲気、間取り、壁や床の状態
- 詳細写真: 水道メーター、ガスメーター、分電盤、配管、コンセント、傷や汚れなどの劣化箇所

ファイル名ごとに、発見したことをリスト形式でまとめてください。
例：
[ファイル名.jpg]
- 内容：キッチンの360度写真
- 指摘事項：
  - シンクに錆びが見られる
  - 壁のタイルが黄ばんでいる
  - 換気扇が古いモデルである
"""

# -----------------------------------------------
# 4. ★★★ メインの処理ロジック ★★★
# -----------------------------------------------
# 「分析開始」ボタンを配置
if st.button("分析を開始する"):
    # GCP認証が成功していて、かつファイルがアップロードされている場合のみ実行
    if GCP_AUTH_SUCCESS and uploaded_files:
        with st.spinner("AIが写真を分析中です...しばらくお待ちください..."):
            try:
                # アップロードされたファイルをAIが読める形式（Partオブジェクト）に変換
                image_parts = []
                for uploaded_file in uploaded_files:
                    # ファイルをバイトデータとして読み込み
                    bytes_data = uploaded_file.getvalue()
                    image_parts.append(
                        Part.from_data(
                            data=bytes_data, 
                            mime_type=uploaded_file.type
                        )
                    )
                
                # プロンプトと全ての画像パートを結合してAIに送信
                contents = [prompt] + image_parts
                response = model.generate_content(contents, request_options={'timeout': 1800})

                # 結果を表示
                st.subheader("分析結果")
                st.markdown(response.text)
                st.success("分析が完了しました！")

            except Exception as e:
                st.error(f"分析中にエラーが発生しました: {e}")

    elif not uploaded_files:
        st.warning("分析するファイルをアップロードしてください。")
    else:
        # GCP認証失敗時のメッセージは既に出ているので、ここでは何もしない
        pass