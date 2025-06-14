#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
現場写真分析・報告書作成システム (Enhanced Version)
====================================================

このアプリケーションは、建設・リフォーム現場の写真を自動分析し、
修繕提案レポートを生成するためのシステムです。

主な機能:
- Google Cloud Vertex AI (Gemini)による画像分析
- バッチ処理による大量画像の効率的な処理
- レポートの編集・保存機能
- PDF出力に最適化されたレイアウト
- セキュアなパスワード認証

技術スタック:
- Streamlit: WebUIフレームワーク
- Vertex AI: Google CloudのAI/MLプラットフォーム
- PIL (Pillow): 画像処理ライブラリ

作成者: [組織名]
バージョン: 2.0.0
最終更新: 2025年1月
"""

import streamlit as st
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import json
import re
from google.oauth2 import service_account
from datetime import date
import math
from PIL import Image
import io
import html
import base64
import gc
import traceback
from typing import Dict, List, Optional, Any, Tuple
import time
import hashlib
from functools import lru_cache
import logging

# ==============================================================================
# 1. アプリケーション設定と定数の定義
# ==============================================================================

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Streamlitのページ設定
st.set_page_config(
    page_title="現場分析レポート - Professional Edition",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'About': "現場写真分析・報告書作成システム v2.0"
    }
)

# アプリケーション定数
class AppConfig:
    """アプリケーションの設定値を管理するクラス"""
    # 画像処理設定
    BATCH_SIZE = 10  # AIに一度に送信する画像の最大枚数
    MAX_IMAGE_WIDTH = 800  # 表示用画像の最大幅（ピクセル）
    JPEG_QUALITY = 85  # JPEG圧縮品質（1-100）
    MAX_FILE_SIZE_MB = 10  # アップロード可能な最大ファイルサイズ（MB）
    
    # AI処理設定
    AI_TIMEOUT_SECONDS = 60  # AI応答のタイムアウト時間
    MAX_RETRIES = 3  # AI処理のリトライ回数
    RETRY_DELAY_SECONDS = 2  # リトライ間隔
    
    # UI設定
    PROGRESS_UPDATE_INTERVAL = 0.1  # プログレスバー更新間隔（秒）
    
    # セキュリティ設定
    SESSION_TIMEOUT_MINUTES = 30  # セッションタイムアウト時間
    MAX_LOGIN_ATTEMPTS = 5  # ログイン試行回数の上限

# ==============================================================================
# 2. セッション状態の管理
# ==============================================================================

class SessionStateManager:
    """
    セッション状態を管理するためのクラス
    
    Streamlitのセッション状態を初期化し、一元管理します。
    これにより、ページリロード時のデータ保持とアプリケーションの
    状態管理が容易になります。
    """
    
    @staticmethod
    def initialize():
        """セッション状態の初期化"""
        # 基本的な状態フラグ
        if 'processing' not in st.session_state:
            st.session_state.processing = False  # 処理中フラグ
            
        if 'report_payload' not in st.session_state:
            st.session_state.report_payload = None  # 生成されたレポートデータ
            
        if 'files_dict' not in st.session_state:
            st.session_state.files_dict = None  # アップロードされたファイルの辞書
            
        if 'edit_mode' not in st.session_state:
            st.session_state.edit_mode = False  # 編集モードフラグ
            
        if 'edited_report' not in st.session_state:
            st.session_state.edited_report = None  # 編集中のレポートデータ
            
        # パフォーマンス最適化用のキャッシュ
        if 'image_cache' not in st.session_state:
            st.session_state.image_cache = {}  # 画像のBase64キャッシュ
            
        # エラー追跡
        if 'error_count' not in st.session_state:
            st.session_state.error_count = 0  # エラー回数のカウント
            
        # ログイン試行回数
        if 'login_attempts' not in st.session_state:
            st.session_state.login_attempts = 0

    @staticmethod
    def clear_cache():
        """キャッシュのクリア（メモリ最適化）"""
        if 'image_cache' in st.session_state:
            st.session_state.image_cache.clear()
        gc.collect()  # ガベージコレクションを強制実行

# ==============================================================================
# 3. セキュリティとパスワード認証
# ==============================================================================

class AuthenticationManager:
    """
    認証機能を管理するクラス
    
    パスワードベースの認証を提供し、不正アクセスを防ぎます。
    ブルートフォース攻撃への対策も含まれています。
    """
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """パスワードのハッシュ値を生成"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def check_password() -> bool:
        """
        パスワード認証を実行
        
        Returns:
            bool: 認証成功時True、それ以外はFalse
        """
        # パスワードの取得（環境変数またはsecrets.tomlから）
        try:
            PASSWORD = st.secrets["PASSWORD"]
        except KeyError:
            st.error("パスワードが設定されていません。")
            st.info("""
                **設定方法:**
                1. `.streamlit/secrets.toml`ファイルを作成
                2. 以下の内容を追加:
                ```toml
                PASSWORD = "your-secure-password"
                ```
            """)
            logger.error("Password not configured in secrets.toml")
            st.stop()
        
        def password_entered():
            """パスワード入力時のコールバック関数"""
            # ログイン試行回数のチェック
            if st.session_state.login_attempts >= AppConfig.MAX_LOGIN_ATTEMPTS:
                st.error("ログイン試行回数の上限に達しました。しばらく待ってから再試行してください。")
                time.sleep(5)  # ブルートフォース対策
                return
            
            # パスワードの検証
            if st.session_state["password"] == PASSWORD:
                st.session_state["password_correct"] = True
                st.session_state.login_attempts = 0  # 成功時はリセット
                del st.session_state["password"]  # パスワードを削除
                logger.info("Authentication successful")
            else:
                st.session_state["password_correct"] = False
                st.session_state.login_attempts += 1
                logger.warning(f"Authentication failed. Attempts: {st.session_state.login_attempts}")
        
        # 認証状態のチェック
        if "password_correct" not in st.session_state:
            # 初回アクセス時
            st.markdown("### ログイン")
            st.text_input(
                "パスワードを入力してください",
                type="password",
                on_change=password_entered,
                key="password",
                placeholder="パスワード"
            )
            return False
            
        elif not st.session_state["password_correct"]:
            # パスワードが間違っている場合
            st.markdown("### ログイン")
            st.text_input(
                "パスワードを入力してください",
                type="password",
                on_change=password_entered,
                key="password",
                placeholder="パスワード"
            )
            
            # エラーメッセージの表示
            remaining_attempts = AppConfig.MAX_LOGIN_ATTEMPTS - st.session_state.login_attempts
            if remaining_attempts > 0:
                st.error(f"パスワードが間違っています。（残り{remaining_attempts}回）")
            else:
                st.error("ログイン試行回数の上限に達しました。")
            return False
        
        return True

# ==============================================================================
# 4. デザインとスタイリング
# ==============================================================================

class StyleManager:
    """
    アプリケーションのスタイルを管理するクラス
    
    CSSの注入とカスタムスタイリングを担当します。
    白基調でミニマル、洗練されたデザインを実現し、
    PDF出力時のレイアウト安定性を確保します。
    """
    
    @staticmethod
    def inject_custom_css():
        """
        カスタムCSSを注入してアプリケーションのスタイルを定義
        
        Note:
            - 印刷用スタイルシートを含む
            - ダークモードを無効化
            - レスポンシブデザインに対応
        """
        st.markdown("""
        <style>
            /* ============================================================
               グローバル設定とテーマ
               ============================================================ */
            
            /* ルート要素の設定 - ライトモードを強制 */
            :root {
                color-scheme: light !important;
                --primary-color: #1f2937;
                --secondary-color: #3b82f6;
                --success-color: #22c55e;
                --warning-color: #f59e0b;
                --danger-color: #dc2626;
                --bg-primary: #ffffff;
                --bg-secondary: #f9fafb;
                --bg-tertiary: #f3f4f6;
                --border-color: #e5e7eb;
                --text-primary: #1f2937;
                --text-secondary: #6b7280;
                --text-tertiary: #9ca3af;
                --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
                --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                --transition-fast: 150ms;
                --transition-normal: 300ms;
            }
            
            /* 基本的な要素のリセットとベーススタイル */
            *, *::before, *::after {
                box-sizing: border-box;
            }
            
            /* Streamlitアプリ全体の背景色とテキスト色 */
            html, body, .stApp, [data-testid="stAppViewContainer"], .main {
                background-color: var(--bg-primary) !important;
                color: var(--text-primary) !important;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 
                            'Helvetica Neue', Arial, sans-serif !important;
                line-height: 1.6;
            }
            
            /* ============================================================
               タイポグラフィ
               ============================================================ */
            
            /* 見出し要素のスタイル */
            h1, h2, h3, h4, h5, h6,
            .stApp h1, .stApp h2, .stApp h3, 
            .stApp h4, .stApp h5, .stApp h6 {
                color: var(--text-primary) !important;
                font-weight: 300 !important;
                letter-spacing: -0.02em !important;
                margin-top: 0;
                margin-bottom: 1rem;
            }
            
            h1 { font-size: 2.5rem !important; }
            h2 { font-size: 2rem !important; }
            h3 { font-size: 1.5rem !important; }
            
            /* 段落とテキスト要素 */
            p, span, label, .stMarkdown, .stText {
                color: var(--text-primary) !important;
            }
            
            /* リンクのスタイル */
            a {
                color: var(--secondary-color) !important;
                text-decoration: none;
                transition: color var(--transition-fast);
            }
            
            a:hover {
                color: #2563eb !important;
                text-decoration: underline;
            }
            
            /* ============================================================
               フォーム要素とインタラクティブコンポーネント
               ============================================================ */
            
            /* 入力フィールドのラベル */
            [data-testid="stTextInput"] label,
            [data-testid="stDateInput"] label,
            [data-testid="stFileUploader"] label,
            [data-testid="stTextArea"] label,
            [data-testid="stSelectbox"] label {
                color: var(--text-primary) !important;
                font-weight: 500 !important;
                font-size: 0.875rem !important;
                letter-spacing: 0.05em !important;
                margin-bottom: 0.5rem !important;
                display: block !important;
            }
            
            /* テキスト入力フィールド共通スタイル */
            input[type="text"], 
            input[type="password"], 
            input[type="date"],
            textarea,
            select {
                width: 100%;
                padding: 0.75rem 1rem;
                background-color: var(--bg-primary) !important;
                color: var(--text-primary) !important;
                border: 1px solid var(--border-color) !important;
                border-radius: 0 !important;
                font-size: 0.875rem !important;
                transition: all var(--transition-fast) !important;
                outline: none;
            }
            
            /* フォーカス時のスタイル */
            input:focus, textarea:focus, select:focus {
                border-color: var(--secondary-color) !important;
                box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1) !important;
            }
            
            /* テキストエリアの追加スタイル */
            textarea {
                resize: vertical;
                min-height: 100px;
            }
            
            /* ファイルアップローダー */
            [data-testid="stFileUploadDropzone"] {
                background-color: var(--bg-secondary) !important;
                border: 2px dashed var(--border-color) !important;
                border-radius: 0 !important;
                padding: 2rem !important;
                text-align: center;
                transition: all var(--transition-normal) !important;
                cursor: pointer;
            }
            
            [data-testid="stFileUploadDropzone"]:hover {
                border-color: var(--secondary-color) !important;
                background-color: var(--bg-tertiary) !important;
            }
            
            [data-testid="stFileUploadDropzone"].st-bu {
                border-color: var(--secondary-color) !important;
                background-color: rgba(59, 130, 246, 0.05) !important;
            }
            
            /* ============================================================
               ボタンスタイル
               ============================================================ */
            
            .stButton > button {
                background-color: var(--bg-primary) !important;
                color: var(--text-primary) !important;
                border: 2px solid var(--text-primary) !important;
                font-weight: 600 !important;
                border-radius: 0 !important;
                padding: 0.75rem 2rem !important;
                letter-spacing: 0.05em !important;
                font-size: 0.875rem !important;
                transition: all var(--transition-fast) !important;
                cursor: pointer;
                text-transform: uppercase;
                min-height: 48px;
            }
            
            .stButton > button:hover:not(:disabled) {
                background-color: var(--text-primary) !important;
                color: var(--bg-primary) !important;
                transform: translateY(-1px) !important;
                box-shadow: var(--shadow-md) !important;
            }
            
            .stButton > button:active:not(:disabled) {
                transform: translateY(0) !important;
                box-shadow: var(--shadow-sm) !important;
            }
            
            .stButton > button:disabled {
                background-color: var(--bg-tertiary) !important;
                color: var(--text-tertiary) !important;
                border-color: var(--border-color) !important;
                cursor: not-allowed;
                opacity: 0.6 !important;
            }
            
            /* プライマリボタン */
            .stButton > button[kind="primary"] {
                background-color: var(--text-primary) !important;
                color: var(--bg-primary) !important;
                border-color: var(--text-primary) !important;
            }
            
            .stButton > button[kind="primary"]:hover:not(:disabled) {
                background-color: #374151 !important;
                border-color: #374151 !important;
            }
            
            /* レポート作成ボタン専用スタイル */
            div[data-testid="column"]:has(button:contains("レポートを作成")) .stButton > button,
            button:contains("レポートを作成") {
                background-color: #1f2937 !important;
                color: #ffffff !important;
                border: 2px solid #1f2937 !important;
                font-weight: 700 !important;
                letter-spacing: 0.05em !important;
                padding: 1rem 2.5rem !important;
                font-size: 1rem !important;
            }
            
            button:contains("レポートを作成"):hover:not(:disabled) {
                background-color: #374151 !important;
                border-color: #374151 !important;
                transform: translateY(-2px) !important;
                box-shadow: 0 8px 16px -2px rgba(0, 0, 0, 0.2) !important;
            }
            
            button:contains("レポートを作成"):disabled,
            button:contains("処理中..."):disabled {
                background-color: #e5e7eb !important;
                color: #9ca3af !important;
                border-color: #e5e7eb !important;
                cursor: not-allowed !important;
                opacity: 0.7 !important;
            }
            
            /* 実行ボタンのコンテナ */
            [data-testid="stButton"][key="submit_button"] > button {
                background-color: #1f2937 !important;
                color: #ffffff !important;
                min-height: 56px !important;
            }
            
            /* ============================================================
               アラートとメッセージ
               ============================================================ */
            
            /* 成功メッセージ */
            .stSuccess, [data-testid="stAlert"][data-baseweb="notification"][kind="success"] {
                background-color: rgba(34, 197, 94, 0.1) !important;
                color: var(--success-color) !important;
                border-left: 4px solid var(--success-color) !important;
                border-radius: 0 !important;
                padding: 1rem 1.5rem !important;
                margin: 1rem 0 !important;
            }
            
            /* 警告メッセージ */
            .stWarning, [data-testid="stAlert"][data-baseweb="notification"][kind="warning"] {
                background-color: rgba(245, 158, 11, 0.1) !important;
                color: var(--warning-color) !important;
                border-left: 4px solid var(--warning-color) !important;
                border-radius: 0 !important;
                padding: 1rem 1.5rem !important;
                margin: 1rem 0 !important;
            }
            
            /* エラーメッセージ */
            .stError, [data-testid="stAlert"][data-baseweb="notification"][kind="error"] {
                background-color: rgba(220, 38, 38, 0.1) !important;
                color: var(--danger-color) !important;
                border-left: 4px solid var(--danger-color) !important;
                border-radius: 0 !important;
                padding: 1rem 1.5rem !important;
                margin: 1rem 0 !important;
            }
            
            /* 情報メッセージ */
            .stInfo, [data-testid="stAlert"][data-baseweb="notification"][kind="info"] {
                background-color: rgba(59, 130, 246, 0.1) !important;
                color: var(--secondary-color) !important;
                border-left: 4px solid var(--secondary-color) !important;
                border-radius: 0 !important;
                padding: 1rem 1.5rem !important;
                margin: 1rem 0 !important;
            }
            
            /* ============================================================
               プログレスバー
               ============================================================ */
            
            .stProgress > div > div {
                background-color: var(--bg-tertiary) !important;
                border-radius: 0 !important;
                height: 8px !important;
                overflow: hidden;
            }
            
            .stProgress > div > div > div {
                background: linear-gradient(90deg, 
                    var(--secondary-color) 0%, 
                    #2563eb 100%) !important;
                border-radius: 0 !important;
                transition: width var(--transition-normal) ease-out;
            }
            
            /* ============================================================
               エクスパンダー
               ============================================================ */
            
            [data-testid="stExpander"] {
                border: 1px solid var(--border-color) !important;
                border-radius: 0 !important;
                background-color: var(--bg-primary) !important;
                margin-bottom: 1rem !important;
                overflow: hidden;
            }
            
            [data-testid="stExpander"] summary {
                background-color: var(--bg-secondary) !important;
                padding: 1rem 1.5rem !important;
                font-weight: 500 !important;
                color: var(--text-primary) !important;
                cursor: pointer;
                transition: background-color var(--transition-fast);
            }
            
            [data-testid="stExpander"] summary:hover {
                background-color: var(--bg-tertiary) !important;
            }
            
            [data-testid="stExpander"] > div > div {
                padding: 1.5rem !important;
            }
            
            /* ============================================================
               カスタムコンポーネント
               ============================================================ */
            
            /* レポートヘッダー */
            .report-header {
                text-align: center;
                padding: 3rem 0 2rem;
                border-bottom: 2px solid var(--border-color);
                margin-bottom: 3rem;
                background: var(--bg-primary);
                position: relative;
            }
            
            .report-header::after {
                content: '';
                position: absolute;
                bottom: -2px;
                left: 50%;
                transform: translateX(-50%);
                width: 100px;
                height: 2px;
                background: var(--text-primary);
            }
            
            .report-header h1 {
                font-size: 2.5rem !important;
                font-weight: 200 !important;
                letter-spacing: -0.03em !important;
                margin-bottom: 1rem !important;
            }
            
            .report-header .report-info {
                display: flex;
                justify-content: center;
                gap: 2rem;
                margin-top: 1rem;
                font-size: 0.875rem;
                color: var(--text-secondary);
            }
            
            /* 印刷ガイダンス */
            .print-guidance {
                background: var(--bg-secondary);
                border: 1px solid var(--border-color);
                border-radius: 0;
                padding: 1.5rem;
                margin-bottom: 3rem;
                position: relative;
            }
            
            .print-guidance strong {
                color: var(--text-primary);
                font-size: 1rem;
                font-weight: 600;
                display: block;
                margin-bottom: 0.5rem;
            }
            
            .print-guidance ol {
                margin: 0;
                padding-left: 1.25rem;
                line-height: 1.8;
            }
            
            /* メトリクスカード */
            .metric-card {
                background: var(--bg-primary);
                border: 1px solid var(--border-color);
                padding: 2rem;
                border-radius: 0;
                text-align: center;
                height: 100%;
                transition: all var(--transition-normal);
                position: relative;
                overflow: hidden;
            }
            
            .metric-card::before {
                content: '';
                position: absolute;
                bottom: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: var(--border-color);
                transition: background var(--transition-fast);
            }
            
            .metric-card:hover {
                border-color: var(--text-secondary);
                box-shadow: var(--shadow-md);
                transform: translateY(-2px);
            }
            
            .metric-card:hover::before {
                background: var(--text-primary);
            }
            
            .metric-value {
                font-size: 3.5rem;
                font-weight: 200;
                margin-bottom: 0.5rem;
                color: var(--text-primary);
                letter-spacing: -0.03em;
                font-variant-numeric: tabular-nums;
            }
            
            .metric-value-high {
                color: var(--danger-color);
                font-weight: 300;
            }
            
            .metric-label {
                font-size: 0.875rem;
                color: var(--text-secondary);
                font-weight: 500;
                letter-spacing: 0.05em;
                text-transform: uppercase;
            }
            
            /* 写真セクション */
            .photo-row {
                display: flex;
                gap: 2rem;
                margin-bottom: 2rem;
                background: var(--bg-primary);
                border: 1px solid var(--border-color);
                border-radius: 0;
                padding: 2rem;
                page-break-inside: avoid;
                break-inside: avoid;
                transition: all var(--transition-normal);
            }
            
            .photo-row:hover {
                box-shadow: var(--shadow-sm);
            }
            
            .photo-container {
                flex: 0 0 300px;
                max-width: 300px;
            }
            
            .photo-img {
                width: 100%;
                height: auto;
                max-height: 225px;
                object-fit: contain;
                border-radius: 0;
                border: 1px solid var(--border-color);
                background: var(--bg-secondary);
                transition: border-color var(--transition-fast);
            }
            
            .photo-row:hover .photo-img {
                border-color: var(--text-secondary);
            }
            
            .content-container {
                flex: 1;
                min-width: 0;
                padding-left: 1.5rem;
            }
            
            .photo-title {
                font-size: 1rem;
                font-weight: 500;
                color: var(--text-primary);
                margin-bottom: 1rem;
                letter-spacing: 0.05em;
                display: flex;
                align-items: baseline;
                gap: 0.5rem;
            }
            
            .photo-title .photo-number {
                font-size: 1.25rem;
                font-weight: 300;
                color: var(--text-secondary);
            }
            
            .photo-filename {
                font-size: 0.75rem;
                color: var(--text-tertiary);
                font-weight: 400;
                font-family: 'Courier New', monospace;
            }
            
            /* 指摘事項のスタイル */
            .finding-item {
                margin-bottom: 0.75rem;
                padding: 0.75rem 1rem;
                border-radius: 0;
                position: relative;
                padding-left: 1.25rem;
                border-left-width: 4px;
                border-left-style: solid;
            }
            
            .finding-high {
                background: rgba(220, 38, 38, 0.05);
                border-left-color: var(--danger-color);
                color: #7f1d1d;
            }
            
            .finding-medium {
                background: rgba(245, 158, 11, 0.05);
                border-left-color: var(--warning-color);
                color: #78350f;
            }
            
            .finding-low {
                background: rgba(59, 130, 246, 0.05);
                border-left-color: var(--secondary-color);
                color: #1e3a8a;
            }
            
            .finding-location {
                font-weight: 600;
                margin-bottom: 0.5rem;
                font-size: 0.875rem;
                letter-spacing: 0.05em;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }
            
            .priority-badge {
                display: inline-block;
                padding: 0.125rem 0.5rem;
                font-size: 0.75rem;
                font-weight: 500;
                letter-spacing: 0.05em;
                text-transform: uppercase;
            }
            
            .priority-badge-high {
                background: var(--danger-color);
                color: white;
            }
            
            .priority-badge-medium {
                background: var(--warning-color);
                color: white;
            }
            
            .priority-badge-low {
                background: var(--secondary-color);
                color: white;
            }
            
            .finding-details {
                line-height: 1.6;
                font-size: 0.875rem;
            }
            
            .finding-details > div {
                margin-bottom: 0.25rem;
                padding-left: 1rem;
                position: relative;
            }
            
            .finding-details > div::before {
                content: '•';
                position: absolute;
                left: 0;
                color: var(--text-secondary);
            }
            
            .observation-box {
                background: rgba(34, 197, 94, 0.05);
                padding: 1rem;
                border-radius: 0;
                color: #14532d;
                font-size: 0.875rem;
                border-left: 4px solid var(--success-color);
            }
            
            .no-finding-box {
                background: rgba(34, 197, 94, 0.05);
                color: #14532d;
                padding: 1rem;
                text-align: center;
                border-radius: 0;
                font-size: 0.875rem;
                border: 1px solid rgba(34, 197, 94, 0.2);
            }
            
            /* 編集モード関連 */
            .edit-mode-banner {
                background: var(--warning-color);
                color: white;
                padding: 0.75rem;
                text-align: center;
                font-weight: 500;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: var(--shadow-md);
            }
            
            .edit-container {
                background: var(--bg-secondary);
                padding: 1.5rem;
                border-radius: 0;
                margin-bottom: 1rem;
                border: 1px solid var(--border-color);
                position: relative;
            }
            
            /* セクションヘッダー */
            .section-header {
                font-size: 1.5rem !important;
                font-weight: 300 !important;
                margin: 3rem 0 1.5rem !important;
                padding-bottom: 0.75rem !important;
                border-bottom: 2px solid var(--border-color) !important;
                position: relative;
            }
            
            .section-header::after {
                content: '';
                position: absolute;
                bottom: -2px;
                left: 0;
                width: 50px;
                height: 2px;
                background: var(--text-primary);
            }
            
            /* ユーティリティクラス */
            .text-muted {
                color: var(--text-secondary) !important;
            }
            
            .text-small {
                font-size: 0.875rem !important;
            }
            
            .mb-0 { margin-bottom: 0 !important; }
            .mb-1 { margin-bottom: 0.5rem !important; }
            .mb-2 { margin-bottom: 1rem !important; }
            .mb-3 { margin-bottom: 1.5rem !important; }
            .mb-4 { margin-bottom: 2rem !important; }
            
            /* 区切り線 */
            hr {
                border: none !important;
                border-top: 1px solid var(--border-color) !important;
                margin: 2rem 0 !important;
                opacity: 0.5;
            }
            
            /* ============================================================
               レスポンシブデザイン
               ============================================================ */
            
            @media (max-width: 768px) {
                .photo-row {
                    flex-direction: column;
                    gap: 1rem;
                }
                
                .photo-container {
                    flex: 1;
                    max-width: 100%;
                }
                
                .content-container {
                    padding-left: 0;
                    padding-top: 1rem;
                }
                
                .report-header .report-info {
                    flex-direction: column;
                    gap: 0.5rem;
                }
                
                .metric-value {
                    font-size: 2.5rem;
                }
            }
            
            /* ============================================================
               印刷用スタイル
               ============================================================ */
            
            @media print {
                /* ページ設定 */
                @page {
                    size: A4;
                    margin: 15mm 10mm 15mm 10mm;
                }
                
                /* 基本設定 */
                body, .stApp {
                    background: white !important;
                    margin: 0 !important;
                    padding: 0 !important;
                }
                
                /* 不要な要素を非表示 */
                header[data-testid="stHeader"],
                [data-testid="stToolbar"],
                .stButton,
                .stTextInput,
                .stTextArea,
                .stSelectbox,
                .stAlert,
                .stProgress,
                .stInfo,
                .stSuccess,
                .stWarning,
                .stError,
                .print-guidance,
                .edit-mode-banner,
                .edit-container,
                button,
                footer {
                    display: none !important;
                }
                
                /* リンクの後のURLを非表示 */
                a[href]:after {
                    content: none !important;
                }
                
                /* 背景色の保持 */
                * {
                    -webkit-print-color-adjust: exact !important;
                    print-color-adjust: exact !important;
                    color-adjust: exact !important;
                }
                
                /* タイトルとヘッダー */
                .report-header {
                    page-break-after: avoid !important;
                    border-bottom: 1px solid #333 !important;
                }
                
                h1, h2, h3, h4, h5, h6 {
                    page-break-after: avoid !important;
                    color: #000 !important;
                }
                
                /* メトリクスカード */
                .metric-card {
                    break-inside: avoid !important;
                    page-break-inside: avoid !important;
                    background: white !important;
                    border: 1px solid #333 !important;
                }
                
                /* 写真セクション */
                .photo-row {
                    page-break-inside: avoid !important;
                    break-inside: avoid !important;
                    margin-bottom: 10px !important;
                    padding: 10px !important;
                    border: 1px solid #333 !important;
                }
                
                .photo-container {
                    flex: 0 0 180px !important;
                    max-width: 180px !important;
                }
                
                .photo-img {
                    max-height: 150px !important;
                    border: 1px solid #333 !important;
                }
                
                /* 指摘事項 */
                .finding-high {
                    background: #fee2e2 !important;
                    border-left: 3px solid #dc2626 !important;
                }
                
                .finding-medium {
                    background: #fef3c7 !important;
                    border-left: 3px solid #f59e0b !important;
                }
                
                .finding-low {
                    background: #dbeafe !important;
                    border-left: 3px solid #3b82f6 !important;
                }
                
                .observation-box {
                    background: #d1fae5 !important;
                    border-left: 3px solid #22c55e !important;
                }
                
                /* フォントサイズの調整 */
                body {
                    font-size: 10pt !important;
                }
                
                .finding-details {
                    font-size: 9pt !important;
                }
                
                .photo-filename {
                    font-size: 8pt !important;
                }
                
                /* ページ番号やヘッダー/フッターの制御 */
                @page {
                    @top-center { content: none; }
                    @bottom-center { content: counter(page); }
                }
            }
            
            /* ============================================================
               アニメーション
               ============================================================ */
            
            @keyframes fadeIn {
                from {
                    opacity: 0;
                    transform: translateY(10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            .fade-in {
                animation: fadeIn var(--transition-normal) ease-out;
            }
            
            @keyframes pulse {
                0%, 100% {
                    opacity: 1;
                }
                50% {
                    opacity: 0.5;
                }
            }
            
            .pulse {
                animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
            }
            
            /* ============================================================
               アクセシビリティ
               ============================================================ */
            
            /* フォーカスリングの改善 */
            :focus-visible {
                outline: 2px solid var(--secondary-color) !important;
                outline-offset: 2px !important;
            }
            
            /* スキップリンク */
            .skip-link {
                position: absolute;
                top: -40px;
                left: 0;
                background: var(--text-primary);
                color: white;
                padding: 8px;
                text-decoration: none;
                z-index: 1000;
            }
            
            .skip-link:focus {
                top: 0;
            }
            
            /* 高コントラストモード対応 */
            @media (prefers-contrast: high) {
                * {
                    border-width: 2px !important;
                }
                
                .metric-value-high {
                    text-decoration: underline;
                    text-decoration-thickness: 3px;
                }
            }
            
            /* モーション設定の尊重 */
            @media (prefers-reduced-motion: reduce) {
                * {
                    animation-duration: 0.01ms !important;
                    animation-iteration-count: 1 !important;
                    transition-duration: 0.01ms !important;
                }
            }
        </style>
        
        <script>
            // 印刷ショートカットのカスタマイズ
            document.addEventListener('keydown', function(e) {
                // Ctrl+P / Cmd+P をインターセプト
                if ((e.ctrlKey || e.metaKey) && e.key === 'p') {
                    e.preventDefault();
                    
                    // カスタムダイアログを表示
                    const message = `PDFとして保存する手順:\\n\\n` +
                        `1. 画面右上の「⋮」メニューをクリック\\n` +
                        `2. 「Print」を選択\\n` +
                        `3. 送信先で「PDFに保存」を選択\\n` +
                        `4. 印刷設定で以下を確認:\\n` +
                        `   • 余白: デフォルト\\n` +
                        `   • 倍率: 100%\\n` +
                        `   • ヘッダーとフッター: オフ\\n` +
                        `5. 「保存」をクリック`;
                    
                    alert(message);
                    return false;
                }
            });
            
            // 画像の遅延読み込み最適化
            if ('IntersectionObserver' in window) {
                const imageObserver = new IntersectionObserver((entries, observer) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            const img = entry.target;
                            img.classList.add('fade-in');
                            observer.unobserve(img);
                        }
                    });
                });
                
                document.addEventListener('DOMContentLoaded', () => {
                    const images = document.querySelectorAll('img[loading="lazy"]');
                    images.forEach(img => imageObserver.observe(img));
                });
            }
            
            // フォーム送信時のボタン無効化
            document.addEventListener('DOMContentLoaded', () => {
                const submitButton = document.querySelector('button[key="submit_button"]');
                if (submitButton) {
                    submitButton.addEventListener('click', () => {
                        setTimeout(() => {
                            submitButton.disabled = true;
                            submitButton.textContent = '処理中...';
                        }, 100);
                    });
                }
            });
        </script>
        """, unsafe_allow_html=True)

# ==============================================================================
# 5. Google Cloud Platform (GCP) 初期化
# ==============================================================================

class GCPManager:
    """
    Google Cloud Platformとの接続を管理するクラス
    
    Vertex AIの初期化と認証を担当します。
    """
    
    @staticmethod
    @st.cache_resource
    def initialize_vertexai() -> Optional[GenerativeModel]:
        """
        Vertex AIを初期化してGenerativeModelインスタンスを返す
        
        Returns:
            GenerativeModel: 初期化されたモデル、失敗時はNone
        """
        try:
            # 認証情報の解析
            if "gcp" not in st.secrets:
                st.error("GCP認証情報が設定されていません。")
                st.info("""
                    **設定方法:**
                    1. `.streamlit/secrets.toml`ファイルに以下を追加:
                    ```toml
                    [gcp]
                    project_id = "your-project-id"
                    gcp_service_account = '''
                    {
                      "type": "service_account",
                      "project_id": "your-project-id",
                      ...
                    }
                    '''
                    ```
                """)
                logger.error("GCP credentials not found in secrets.toml")
                return None
            
            # 認証情報の解析
            gcp_secrets = st.secrets["gcp"]
            service_account_info = json.loads(gcp_secrets["gcp_service_account"])
            
            # サービスアカウントの認証情報を作成
            credentials = service_account.Credentials.from_service_account_info(
                service_account_info
            )
            
            # Vertex AIを初期化
            vertexai.init(
                project=gcp_secrets["project_id"],
                location="asia-northeast1",  # 東京リージョン
                credentials=credentials
            )
            
            # Gemini Proモデルを初期化
            model = GenerativeModel("gemini-1.5-pro")
            logger.info(f"Successfully initialized Vertex AI for project: {gcp_secrets['project_id']}")
            
            return model
            
        except json.JSONDecodeError as e:
            st.error("GCP認証情報のJSON形式が正しくありません。")
            logger.error(f"JSON decode error: {str(e)}")
            return None
            
        except Exception as e:
            st.error(f"GCP認証の初期化に失敗しました: {str(e)}")
            logger.error(f"GCP initialization error: {str(e)}\n{traceback.format_exc()}")
            return None

# ==============================================================================
# 6. AI処理とプロンプトエンジニアリング
# ==============================================================================

class AIProcessor:
    """
    AI処理を管理するクラス
    
    画像分析のプロンプト生成、AI応答の処理、エラーハンドリングを担当します。
    """
    
    @staticmethod
    def create_report_prompt(filenames: List[str]) -> str:
        """
        AI分析用のプロンプトを生成
        
        Args:
            filenames: 分析対象のファイル名リスト
            
        Returns:
            str: 構造化されたプロンプト文字列
        """
        # ファイル名リストを整形
        file_list_str = "\n".join([f"- {name}" for name in filenames])
        
        # プロンプトテンプレート
        prompt = f"""
        あなたは、日本のリフォーム・原状回復工事を専門とする、25年以上の経験を持つ現場監督です。
        建築基準法、消防法、労働安全衛生法などの関連法規に精通し、一級建築施工管理技士の資格を保有しています。
        
        あなたの仕事は、提供された現場写真を詳細に分析し、クライアントに提出するための
        プロフェッショナルで分かりやすい修繕提案レポートを作成することです。
        
        【分析の観点】
        1. 安全性: 構造的な問題、安全上のリスク
        2. 機能性: 設備の動作不良、使用上の問題
        3. 美観性: 外観の劣化、汚損、損傷
        4. 法規適合性: 建築基準法、消防法等への適合
        5. 経済性: 修繕の緊急度とコストバランス
        
        【写真分析の手順】
        各写真について以下の手順で分析してください：
        1. 写真全体を観察し、撮影場所と対象物を特定
        2. 目視可能なすべての要素を詳細にチェック
        3. 劣化、損傷、不具合の兆候を探索
        4. 安全性、機能性、美観性の観点から評価
        5. 修繕の必要性と緊急度を判断
        
        【出力形式】
        **重要**: 出力は純粋なJSON形式のみとし、```json```などのマークダウンや説明文は含めないでください。
        
        以下のJSON構造で出力してください：
        [
            {{
                "file_name": "写真ファイル名",
                "findings": [
                    {{
                        "location": "具体的な場所（例：南側外壁上部、1階トイレ便器等）",
                        "current_state": "現状の詳細な説明（劣化度合い、症状等を具体的に）",
                        "suggested_work": "推奨する工事内容（工法、材料、作業内容を具体的に）",
                        "priority": "高/中/低（判断基準を明確に）",
                        "notes": "補足事項（概算費用、工期の目安、注意点等）"
                    }}
                ],
                "observation": "findings が空の場合のみ記載。設備の型番、メーカー、状態等を記述"
            }}
        ]
        
        【緊急度の判断基準】
        - 高: 安全上のリスク、法規違反、機能停止の恐れがある（1ヶ月以内の対応推奨）
        - 中: 機能低下、進行性の劣化がある（3-6ヶ月以内の対応推奨）
        - 低: 美観上の問題、予防的措置（1年以内の対応で可）
        
        【分析対象ファイル】
        {file_list_str}
        
        それでは、上記の写真を順番に詳細に分析してください。
        """
        
        return prompt
    
    @staticmethod
    def generate_ai_report(
        model: GenerativeModel,
        file_batch: List[Any],
        prompt: str,
        retry_count: int = 0
    ) -> Optional[str]:
        """
        AI APIを呼び出してレポートを生成（リトライ機能付き）
        
        Args:
            model: Vertex AIのモデルインスタンス
            file_batch: 分析する画像ファイルのリスト
            prompt: AIへのプロンプト
            retry_count: 現在のリトライ回数
            
        Returns:
            str: AI応答テキスト、失敗時はNone
        """
        try:
            # 画像データをVertex AI用のPartオブジェクトに変換
            image_parts = []
            for f in file_batch:
                try:
                    f.seek(0)  # ファイルポインタをリセット
                    image_data = f.read()
                    image_part = Part.from_data(
                        data=image_data,
                        mime_type=f.type
                    )
                    image_parts.append(image_part)
                except Exception as e:
                    logger.error(f"Error processing image {f.name}: {str(e)}")
                                            st.warning(f"⚠️ 画像 {f.name} の処理中にエラーが発生しました")
                        continue  # エラーがあっても他の画像の処理を続行
            
            if not image_parts:
                raise ValueError("処理可能な画像がありません")
            
            # タイムアウトを設定してAI APIを呼び出し
            with st.spinner(f"AI分析中... (画像数: {len(image_parts)})"):
                response = model.generate_content(
                    [prompt] + image_parts,
                    generation_config={
                        "temperature": 0.2,  # 一貫性のある出力のため低めに設定
                        "top_p": 0.8,
                        "top_k": 40,
                        "max_output_tokens": 8192,
                    }
                )
            
            # 応答の検証
            if not response or not response.text:
                raise ValueError("AIからの応答が空です")
            
            logger.info(f"Successfully generated AI report for {len(file_batch)} images")
            return response.text
            
        except Exception as e:
            logger.error(f"AI report generation error (attempt {retry_count + 1}): {str(e)}")
            
            # リトライ処理
            if retry_count < AppConfig.MAX_RETRIES - 1:
                time.sleep(AppConfig.RETRY_DELAY_SECONDS * (retry_count + 1))
                return AIProcessor.generate_ai_report(
                    model, file_batch, prompt, retry_count + 1
                )
            else:
                st.error(f"❌ AI分析に失敗しました: {str(e)}")
                return None
    
    @staticmethod
    def parse_json_response(text: str) -> Optional[List[Dict]]:
        """
        AI応答からJSONを抽出して解析（複数の解析戦略を使用）
        
        Args:
            text: AI応答のテキスト
            
        Returns:
            List[Dict]: 解析されたJSONデータ、失敗時はNone
        """
        if not text:
            return None
        
        # 戦略1: 直接JSON解析を試みる
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 戦略2: コードブロックからJSONを抽出
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 戦略3: 配列の開始と終了を探す
        array_match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
        if array_match:
            try:
                return json.loads(array_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # 戦略4: 改行やエスケープ文字を修正して再試行
        cleaned_text = text.strip()
        cleaned_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned_text)  # 制御文字を削除
        cleaned_text = re.sub(r'\\(?!["\\/bfnrt])', r'\\\\', cleaned_text)  # 不正なエスケープを修正
        
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {str(e)}")
            logger.debug(f"Failed to parse text: {text[:500]}...")  # デバッグ用
            
            # エラー詳細を表示
            st.error("AI応答をJSON形式として解析できませんでした")
            with st.expander("エラー詳細を表示"):
                st.code(text, language="text")
                st.error(f"JSONエラー: {str(e)}")
            
            return None

# ==============================================================================
# 7. 画像処理とパフォーマンス最適化
# ==============================================================================

class ImageProcessor:
    """
    画像処理とパフォーマンス最適化を担当するクラス
    
    大量の画像を効率的に処理し、メモリ使用量を最小限に抑えます。
    """
    
    @staticmethod
    @lru_cache(maxsize=100)
    def get_image_hash(image_bytes: bytes) -> str:
        """画像のハッシュ値を生成（キャッシュ用）"""
        return hashlib.md5(image_bytes).hexdigest()
    
    @staticmethod
    def optimize_image_for_display(
        file_obj: Any,
        max_width: int = AppConfig.MAX_IMAGE_WIDTH,
        quality: int = AppConfig.JPEG_QUALITY
    ) -> Optional[str]:
        """
        画像を最適化してBase64エンコード（メモリ効率を考慮）
        
        Args:
            file_obj: 画像ファイルオブジェクト
            max_width: 最大幅（ピクセル）
            quality: JPEG品質（1-100）
            
        Returns:
            str: Base64エンコードされた画像データ、失敗時はNone
        """
        try:
            # ファイルポインタをリセット
            file_obj.seek(0)
            
            # キャッシュチェック
            file_bytes = file_obj.read()
            file_hash = ImageProcessor.get_image_hash(file_bytes)
            
            if 'image_cache' in st.session_state and file_hash in st.session_state.image_cache:
                logger.debug(f"Using cached image: {file_hash}")
                return st.session_state.image_cache[file_hash]
            
            # PILで画像を開く
            file_obj.seek(0)
            img = Image.open(file_obj)
            
            # EXIF情報に基づいて画像を回転
            try:
                exif = img._getexif()
                if exif:
                    orientation = exif.get(0x0112)
                    if orientation:
                        rotations = {
                            3: 180,
                            6: 270,
                            8: 90
                        }
                        if orientation in rotations:
                            img = img.rotate(rotations[orientation], expand=True)
            except:
                pass  # EXIF処理エラーは無視
            
            # 画像が大きすぎる場合はリサイズ
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize(
                    (max_width, new_height),
                    Image.Resampling.LANCZOS
                )
                logger.debug(f"Resized image from {img.width}x{img.height} to {max_width}x{new_height}")
            
            # RGBモードに変換（透明度を白背景で合成）
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # JPEGとして保存（メモリ上）
            output = io.BytesIO()
            img.save(
                output,
                format='JPEG',
                quality=quality,
                optimize=True,
                progressive=True
            )
            output.seek(0)
            
            # Base64エンコード
            img_base64 = base64.b64encode(output.read()).decode()
            
            # キャッシュに保存（メモリ制限を考慮）
            if 'image_cache' not in st.session_state:
                st.session_state.image_cache = {}
            
            # キャッシュサイズ制限（100枚まで）
            if len(st.session_state.image_cache) >= 100:
                # 最も古いアイテムを削除
                oldest_key = next(iter(st.session_state.image_cache))
                del st.session_state.image_cache[oldest_key]
            
            st.session_state.image_cache[file_hash] = img_base64
            
            # メモリ解放
            img.close()
            output.close()
            
            return img_base64
            
        except Exception as e:
            logger.error(f"Image optimization error: {str(e)}")
            st.warning(f"画像の最適化中にエラーが発生しました: {str(e)}")
            
            # フォールバック: 元の画像をそのままBase64エンコード
            try:
                file_obj.seek(0)
                return base64.b64encode(file_obj.read()).decode()
            except:
                return None

# ==============================================================================
# 8. レポート表示と編集機能
# ==============================================================================

class ReportRenderer:
    """
    レポートの表示と編集機能を管理するクラス
    
    読み取り専用表示と編集可能な表示の両方をサポートします。
    """
    
    @staticmethod
    def create_photo_row_html(
        index: int,
        item: Dict[str, Any],
        img_base64: Optional[str] = None
    ) -> str:
        """
        写真と内容を横並びで表示するHTMLを生成（読み取り専用）
        
        Args:
            index: 写真の番号
            item: レポートデータの1アイテム
            img_base64: Base64エンコードされた画像データ
            
        Returns:
            str: 生成されたHTML文字列
        """
        # XSS対策のためHTMLエスケープ
        file_name = html.escape(str(item.get('file_name', '')))
        findings = item.get("findings", [])
        
        # 写真部分のHTML
        if img_base64:
            photo_html = f'''
                <img src="data:image/jpeg;base64,{img_base64}" 
                     class="photo-img" 
                     loading="lazy"
                     alt="現場写真 {index}: {file_name}">
            '''
        else:
            photo_html = '''
                <div style="height: 150px; background: #f3f4f6; 
                     display: flex; align-items: center; justify-content: center; 
                     border: 1px solid #e5e7eb;">
                    <span style="color: #9ca3af;">画像を読み込めません</span>
                </div>
            '''
        
        # コンテンツ部分のHTML生成
        content_html = f'''
            <div class="photo-title">
                <span class="photo-number">{index}.</span>
                <span class="photo-filename">{file_name}</span>
            </div>
        '''
        
        if findings:
            # 指摘事項がある場合
            for finding in findings:
                priority = finding.get('priority', '中')
                priority_class = {
                    '高': 'finding-high',
                    '中': 'finding-medium',
                    '低': 'finding-low'
                }.get(priority, 'finding-medium')
                
                priority_badge_class = {
                    '高': 'priority-badge-high',
                    '中': 'priority-badge-medium',
                    '低': 'priority-badge-low'
                }.get(priority, 'priority-badge-medium')
                
                # 各フィールドをエスケープ
                location = html.escape(str(finding.get('location', 'N/A')))
                current_state = html.escape(str(finding.get('current_state', 'N/A')))
                suggested_work = html.escape(str(finding.get('suggested_work', 'N/A')))
                
                content_html += f'''
                    <div class="finding-item {priority_class}">
                        <div class="finding-location">
                            {location}
                            <span class="priority-badge {priority_badge_class}">{priority}</span>
                        </div>
                        <div class="finding-details">
                            <div><strong>現状:</strong> {current_state}</div>
                            <div><strong>提案:</strong> {suggested_work}</div>
                '''
                
                # 備考がある場合
                if finding.get('notes'):
                    notes = html.escape(str(finding.get('notes', '')))
                    content_html += f'<div><strong>備考:</strong> {notes}</div>'
                
                content_html += '</div></div>'
                
        elif item.get("observation"):
            # 所見のみの場合
            observation = html.escape(str(item.get('observation', '')))
            content_html += f'<div class="observation-box">{observation}</div>'
        else:
            # 指摘事項なしの場合
            content_html += '<div class="no-finding-box">修繕必要箇所なし</div>'
        
        # 全体のHTML
        return f'''
            <div class="photo-row fade-in">
                <div class="photo-container">
                    {photo_html}
                </div>
                <div class="content-container">
                    {content_html}
                </div>
            </div>
        '''
    
    @staticmethod
    def display_full_report(
        report_payload: Dict[str, Any],
        files_dict: Optional[Dict[str, Any]]
    ) -> None:
        """
        読み取り専用のレポートを表示
        
        Args:
            report_payload: レポートデータ
            files_dict: ファイル名をキーとした画像ファイルの辞書
        """
        report_data = report_payload.get('report_data', [])
        report_title = report_payload.get('title', '')
        survey_date = report_payload.get('date', '')
        
        # レポートヘッダー
        st.markdown(f'''
            <div class="report-header">
                <h1>現場分析レポート</h1>
                <div class="report-info">
                    <div><strong>物件名:</strong> {html.escape(report_title or '（未設定）')}</div>
                    <div><strong>調査日:</strong> {html.escape(survey_date)}</div>
                </div>
            </div>
        ''', unsafe_allow_html=True)
        
        # サマリー計算
        total_findings = sum(len(item.get("findings", [])) for item in report_data)
        high_priority_count = sum(
            1 for item in report_data
            for f in item.get("findings", [])
            if f.get("priority") == "高"
        )
        medium_priority_count = sum(
            1 for item in report_data
            for f in item.get("findings", [])
            if f.get("priority") == "中"
        )
        low_priority_count = sum(
            1 for item in report_data
            for f in item.get("findings", [])
            if f.get("priority") == "低"
        )
        
        # サマリー表示
        st.markdown('<h2 class="section-header">分析結果サマリー</h2>', unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f'''
                <div class="metric-card">
                    <div class="metric-value">{len(report_data)}</div>
                    <div class="metric-label">分析写真数</div>
                </div>
            ''', unsafe_allow_html=True)
        
        with col2:
            st.markdown(f'''
                <div class="metric-card">
                    <div class="metric-value">{total_findings}</div>
                    <div class="metric-label">総指摘件数</div>
                </div>
            ''', unsafe_allow_html=True)
        
        with col3:
            st.markdown(f'''
                <div class="metric-card">
                    <div class="metric-value metric-value-high">{high_priority_count}</div>
                    <div class="metric-label">緊急度「高」</div>
                </div>
            ''', unsafe_allow_html=True)
        
        with col4:
            st.markdown(f'''
                <div class="metric-card">
                    <div class="metric-value">{medium_priority_count}/{low_priority_count}</div>
                    <div class="metric-label">中/低優先度</div>
                </div>
            ''', unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 詳細分析結果
        st.markdown('<h2 class="section-header">詳細分析結果</h2>', unsafe_allow_html=True)
        
        # デバッグ用：レポートデータの構造を確認
        if st.secrets.get("debug_mode", False):
            with st.expander("デバッグ: レポートデータ構造"):
                st.json(report_data[0] if report_data else {})
        
        # プログレスバーで画像処理状況を表示
        if len(report_data) > 10:  # 10枚以上の場合のみプログレスバーを表示
            progress_bar = st.progress(0)
            status_text = st.empty()
        else:
            progress_bar = None
            status_text = None
        
        # 各写真を横並びレイアウトで表示
        for i, item in enumerate(report_data):
            # 進捗状況を更新
            if progress_bar:
                progress = (i + 1) / len(report_data)
                progress_bar.progress(progress)
                status_text.text(f"画像を処理中... ({i + 1}/{len(report_data)})")
            
            # 画像の最適化とBase64エンコード
            img_base64 = None
            if files_dict and item.get('file_name') in files_dict:
                file_obj = files_dict[item['file_name']]
                img_base64 = ImageProcessor.optimize_image_for_display(file_obj)
            
            # 横並びの写真行を表示
            photo_row_html = ReportRenderer.create_photo_row_html(i + 1, item, img_base64)
            # HTMLが正しく生成されているか確認
            if photo_row_html and isinstance(photo_row_html, str):
                st.markdown(photo_row_html, unsafe_allow_html=True)
            else:
                st.error(f"写真 {i + 1} の表示でエラーが発生しました")
            
            # メモリ効率のため定期的にガベージコレクション
            if i % 20 == 0:
                gc.collect()
        
        # プログレスバーを削除
        if progress_bar:
            progress_bar.empty()
            status_text.empty()
    
    @staticmethod
    def display_editable_report(
        report_payload: Dict[str, Any],
        files_dict: Optional[Dict[str, Any]]
    ) -> None:
        """
        編集可能なレポートを表示
        
        Args:
            report_payload: レポートデータ
            files_dict: ファイル名をキーとした画像ファイルの辞書
        """
        # 編集モードバナー
        st.markdown(
            '<div class="edit-mode-banner">編集モード - 変更後は「編集を保存」をクリックしてください</div>',
            unsafe_allow_html=True
        )
        
        # 編集用データの初期化
        if st.session_state.edited_report is None:
            st.session_state.edited_report = json.loads(json.dumps(report_payload))
        
        report_data = st.session_state.edited_report.get('report_data', [])
        report_title = st.session_state.edited_report.get('title', '')
        survey_date = st.session_state.edited_report.get('date', '')
        
        # ヘッダー情報の編集
        st.markdown('<h2 class="section-header">レポート情報</h2>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            new_title = st.text_input(
                "物件名",
                value=report_title,
                key="edit_title"
            )
            st.session_state.edited_report['title'] = new_title
        
        with col2:
            # 日付文字列をdateオブジェクトに変換
            try:
                date_obj = date.fromisoformat(survey_date.replace('年', '-').replace('月', '-').replace('日', ''))
            except:
                date_obj = date.today()
            
            new_date = st.date_input(
                "調査日",
                value=date_obj,
                key="edit_date"
            )
            st.session_state.edited_report['date'] = new_date.strftime('%Y年%m月%d日')
        
        st.markdown("---")
        
        # 詳細分析結果の編集
        st.markdown('<h2 class="section-header">詳細分析結果の編集</h2>', unsafe_allow_html=True)
        
        # 各写真を編集可能な形で表示
        for i, item in enumerate(report_data):
            with st.container():
                st.markdown(f'<div class="edit-container">', unsafe_allow_html=True)
                
                # 写真と基本情報の表示
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    # 写真表示
                    if files_dict and item.get('file_name') in files_dict:
                        try:
                            file_obj = files_dict[item['file_name']]
                            img_base64 = ImageProcessor.optimize_image_for_display(file_obj)
                            st.markdown(
                                f'<img src="data:image/jpeg;base64,{img_base64}" '
                                f'class="photo-img" alt="写真 {i + 1}">',
                                unsafe_allow_html=True
                            )
                        except Exception as e:
                            st.error(f"画像の表示エラー: {str(e)}")
                    else:
                        st.info("画像なし")
                    
                    # ファイル名表示
                    st.markdown(
                        f'<p class="text-small text-muted mb-0">'
                        f'{i + 1}. {html.escape(item.get("file_name", ""))}</p>',
                        unsafe_allow_html=True
                    )
                
                with col2:
                    findings = item.get("findings", [])
                    
                    if findings:
                        # 指摘事項の編集
                        findings_to_delete = []
                        
                        for j, finding in enumerate(findings):
                            current_location = finding.get('location', '')
                            current_priority = finding.get('priority', '中')
                            
                            # エクスパンダーのタイトルを動的に更新
                            expander_title = f"指摘事項 {j + 1}"
                            if current_location:
                                expander_title += f": {current_location}"
                            expander_title += f" [{current_priority}]"
                            
                            with st.expander(expander_title, expanded=True):
                                # 編集フォーム
                                finding['location'] = st.text_input(
                                    "場所",
                                    value=finding.get('location', ''),
                                    key=f"location_{i}_{j}",
                                    placeholder="例: 南側外壁上部"
                                )
                                
                                finding['current_state'] = st.text_area(
                                    "現状",
                                    value=finding.get('current_state', ''),
                                    key=f"current_{i}_{j}",
                                    height=80,
                                    placeholder="例: 塗装の剥離と亀裂が確認される"
                                )
                                
                                finding['suggested_work'] = st.text_area(
                                    "提案する工事内容",
                                    value=finding.get('suggested_work', ''),
                                    key=f"suggest_{i}_{j}",
                                    height=80,
                                    placeholder="例: 高圧洗浄後、下地補修を行い、シリコン塗料で塗装"
                                )
                                
                                # 緊急度選択
                                priority_options = ['高', '中', '低']
                                current_priority_index = priority_options.index(
                                    finding.get('priority', '中')
                                    if finding.get('priority', '中') in priority_options
                                    else '中'
                                )
                                
                                col_p1, col_p2 = st.columns([3, 1])
                                with col_p1:
                                    finding['priority'] = st.selectbox(
                                        "緊急度",
                                        options=priority_options,
                                        index=current_priority_index,
                                        key=f"priority_{i}_{j}",
                                        help="高: 1ヶ月以内、中: 3-6ヶ月以内、低: 1年以内"
                                    )
                                
                                finding['notes'] = st.text_area(
                                    "備考",
                                    value=finding.get('notes', ''),
                                    key=f"notes_{i}_{j}",
                                    height=60,
                                    placeholder="例: 概算費用30万円、工期3日"
                                )
                                
                                # 削除ボタン
                                if st.button(
                                    "この指摘事項を削除",
                                    key=f"delete_{i}_{j}",
                                    type="secondary"
                                ):
                                    findings_to_delete.append(j)
                        
                        # 削除処理
                        for idx in reversed(findings_to_delete):
                            st.session_state.edited_report['report_data'][i]['findings'].pop(idx)
                            st.rerun()
                        
                        # 新規指摘事項追加ボタン
                        if st.button(
                            "指摘事項を追加",
                            key=f"add_finding_{i}",
                            use_container_width=True
                        ):
                            st.session_state.edited_report['report_data'][i]['findings'].append({
                                'location': '',
                                'current_state': '',
                                'suggested_work': '',
                                'priority': '中',
                                'notes': ''
                            })
                            st.rerun()
                    
                    elif item.get("observation"):
                        # 所見の編集
                        st.session_state.edited_report['report_data'][i]['observation'] = st.text_area(
                            "所見",
                            value=item.get('observation', ''),
                            key=f"observation_{i}",
                            height=100,
                            placeholder="例: TOTO製トイレ、型番TCF8GM23。目立った傷や汚れなし。"
                        )
                        
                        # 指摘事項に変更ボタン
                        if st.button(
                            "指摘事項に変更",
                            key=f"convert_{i}",
                            use_container_width=True
                        ):
                            st.session_state.edited_report['report_data'][i]['observation'] = ''
                            st.session_state.edited_report['report_data'][i]['findings'] = [{
                                'location': '',
                                'current_state': '',
                                'suggested_work': '',
                                'priority': '中',
                                'notes': ''
                            }]
                            st.rerun()
                    else:
                        # 修繕必要箇所なし
                        st.info("修繕必要箇所なし")
                        
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button(
                                "指摘事項を追加",
                                key=f"add_new_finding_{i}",
                                use_container_width=True
                            ):
                                if 'findings' not in st.session_state.edited_report['report_data'][i]:
                                    st.session_state.edited_report['report_data'][i]['findings'] = []
                                st.session_state.edited_report['report_data'][i]['findings'].append({
                                    'location': '',
                                    'current_state': '',
                                    'suggested_work': '',
                                    'priority': '中',
                                    'notes': ''
                                })
                                st.rerun()
                        
                        with col_btn2:
                            if st.button(
                                "所見を追加",
                                key=f"add_new_observation_{i}",
                                use_container_width=True
                            ):
                                st.session_state.edited_report['report_data'][i]['observation'] = ''
                                st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)
                st.markdown("---")

# ==============================================================================
# 9. メインアプリケーション
# ==============================================================================

def main():
    """
    メインアプリケーションのエントリーポイント
    
    アプリケーションの全体的な流れを制御します。
    """
    # CSSを最初に注入
    StyleManager.inject_custom_css()
    
    # セッション状態の初期化
    SessionStateManager.initialize()
    
    # パスワード認証
    if not AuthenticationManager.check_password():
        return
    
    # Vertex AIモデルの初期化
    model = GCPManager.initialize_vertexai()
    if not model:
        st.error("AIモデルの初期化に失敗しました。設定を確認してください。")
        return
    
    # ============================================================
    # 状態1: レポートが生成済みの場合
    # ============================================================
    if st.session_state.report_payload is not None:
        st.success("レポートの作成が完了しました")
        
        # アクションボタン
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            if st.session_state.edit_mode:
                if st.button(
                    "編集を保存",
                    key="save_edit",
                    use_container_width=True,
                    type="primary"
                ):
                    # 編集内容を保存
                    st.session_state.report_payload = json.loads(
                        json.dumps(st.session_state.edited_report)
                    )
                    st.session_state.edit_mode = False
                    st.session_state.edited_report = None
                    st.success("編集内容を保存しました")
                    time.sleep(1)
                    st.rerun()
            else:
                if st.button(
                    "レポートを編集",
                    key="start_edit",
                    use_container_width=True
                ):
                    st.session_state.edit_mode = True
                    st.session_state.edited_report = None
                    st.rerun()
        
        with col2:
            if st.session_state.edit_mode:
                if st.button(
                    "編集をキャンセル",
                    key="cancel_edit",
                    use_container_width=True,
                    type="secondary"
                ):
                    if st.button("本当にキャンセルしますか？", key="confirm_cancel"):
                        st.session_state.edit_mode = False
                        st.session_state.edited_report = None
                        st.rerun()
            else:
                # JSONダウンロードボタン
                report_json = json.dumps(
                    st.session_state.report_payload,
                    ensure_ascii=False,
                    indent=2
                )
                st.download_button(
                    label="JSONダウンロード",
                    data=report_json,
                    file_name=f"report_{date.today().strftime('%Y%m%d')}.json",
                    mime="application/json",
                    use_container_width=True
                )
        
        with col3:
            if st.button(
                "新しいレポートを作成",
                key="new_from_result",
                use_container_width=True,
                type="secondary"
            ):
                # 確認ダイアログ
                if st.button("現在のレポートは削除されます。続行しますか？", key="confirm_new"):
                    SessionStateManager.clear_cache()
                    st.session_state.clear()
                    st.rerun()
        
        # 印刷ガイダンス（表示モードのみ）
        if not st.session_state.edit_mode:
            st.markdown("""
                <div class="print-guidance">
                    <strong>PDFとして保存する方法</strong>
                    <ol>
                        <li>画面右上の「⋮」（3点メニュー）をクリック</li>
                        <li>「Print」を選択</li>
                        <li>送信先で「PDFに保存」を選択</li>
                        <li>印刷設定で「ヘッダーとフッター」のチェックを外す</li>
                        <li>「保存」をクリック</li>
                    </ol>
                </div>
            """, unsafe_allow_html=True)
        
        # レポート表示
        if st.session_state.edit_mode:
            ReportRenderer.display_editable_report(
                st.session_state.report_payload,
                st.session_state.files_dict
            )
        else:
            ReportRenderer.display_full_report(
                st.session_state.report_payload,
                st.session_state.files_dict
            )
        
        return
    
    # ============================================================
    # 状態2: 初期画面（入力フォーム）
    # ============================================================
    
    # タイトルとヘッダー
    st.markdown("""
        <div style="text-align: center; padding: 2rem 0; margin-bottom: 2rem;">
            <h1 style="font-size: 3rem; font-weight: 200; margin-bottom: 0.5rem;">
                現場写真分析システム
            </h1>
            <p style="font-size: 1.2rem; color: #6b7280; font-weight: 300;">
                Professional Site Analysis & Reporting
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # 使い方の説明
    with st.expander("使い方ガイド", expanded=False):
        st.markdown("""
            ### このシステムでできること
            - 現場写真から修繕箇所を自動検出
            - 緊急度別の分析レポート作成
            - レポートの編集・カスタマイズ
            - PDF形式での出力
            
            ### 使用手順
            1. **物件情報を入力** - 物件名と調査日を設定
            2. **写真をアップロード** - 複数枚まとめて選択可能
            3. **AI分析を実行** - 「レポートを作成」ボタンをクリック
            4. **レポートを確認・編集** - 必要に応じて内容を修正
            5. **PDFとして保存** - ブラウザの印刷機能を使用
            
            ### 推奨事項
            - 写真は明るく鮮明なものを使用
            - 1枚あたり10MB以下を推奨
            - スマートフォンで撮影した写真もOK
            - 一度に最大50枚まで処理可能
        """)
    
    # 処理中の場合の警告
    if st.session_state.processing:
        st.warning("現在処理中です。しばらくお待ちください...")
    
    # 入力フォーム
    st.markdown('<h2 class="section-header">物件情報の入力</h2>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        report_title = st.text_input(
            "物件名・案件名",
            placeholder="例: 〇〇ビル 301号室 原状回復工事",
            disabled=st.session_state.processing,
            help="レポートのタイトルに使用されます"
        )
    
    with col2:
        survey_date = st.date_input(
            "調査日",
            value=date.today(),
            disabled=st.session_state.processing,
            help="現場調査を実施した日付"
        )
    
    st.markdown('<h2 class="section-header">写真のアップロード</h2>', unsafe_allow_html=True)
    
    # ファイルアップローダー
    uploaded_files = st.file_uploader(
        "分析したい写真を選択してください",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="file_uploader",
        disabled=st.session_state.processing,
        help=f"対応形式: PNG, JPG, JPEG（最大{AppConfig.MAX_FILE_SIZE_MB}MB/枚）"
    )
    
    # アップロード状況の表示
    if uploaded_files and not st.session_state.processing:
        # ファイルサイズチェック
        oversized_files = []
        total_size = 0
        
        for file in uploaded_files:
            file_size_mb = file.size / (1024 * 1024)
            total_size += file_size_mb
            if file_size_mb > AppConfig.MAX_FILE_SIZE_MB:
                oversized_files.append(f"{file.name} ({file_size_mb:.1f}MB)")
        
        if oversized_files:
            st.error(f"以下のファイルはサイズ制限（{AppConfig.MAX_FILE_SIZE_MB}MB）を超えています:")
            for file in oversized_files:
                st.write(f"  • {file}")
        else:
            col1, col2 = st.columns(2)
            with col1:
                st.success(f"{len(uploaded_files)}枚の写真がアップロードされました")
            with col2:
                st.info(f"合計サイズ: {total_size:.1f}MB")
            
            # プレビュー表示（最初の3枚）
            if len(uploaded_files) > 0:
                with st.expander("アップロード画像のプレビュー", expanded=False):
                    preview_cols = st.columns(min(3, len(uploaded_files)))
                    for i, (col, file) in enumerate(zip(preview_cols, uploaded_files[:3])):
                        with col:
                            try:
                                img = Image.open(file)
                                st.image(img, caption=file.name, use_container_width=True)
                            except:
                                st.error(f"プレビューエラー: {file.name}")
                    
                    if len(uploaded_files) > 3:
                        st.info(f"他 {len(uploaded_files) - 3}枚...")
    
    # 実行ボタン
    st.markdown("---")
    
    # ボタン用のカスタムスタイル
    if not st.session_state.processing:
        st.markdown("""
            <style>
                div.stButton:last-of-type > button {
                    background-color: #1f2937 !important;
                    color: #ffffff !important;
                    font-weight: 700 !important;
                }
                div.stButton:last-of-type > button:hover {
                    background-color: #374151 !important;
                }
            </style>
        """, unsafe_allow_html=True)
    
    button_label = "⏳ 処理中..." if st.session_state.processing else "🚀 レポートを作成"
    button_disabled = not uploaded_files or st.session_state.processing or not report_title
    
    # 必須項目のチェック
    if not report_title and uploaded_files:
        st.warning("⚠️ 物件名を入力してください")
    
    submitted = st.button(
        button_label,
        type="primary",
        use_container_width=True,
        disabled=button_disabled,
        key="submit_button",
        help="すべての必須項目を入力してからクリックしてください"
    )
    
    # 処理の実行
    if submitted and not st.session_state.processing and uploaded_files and report_title:
        # 処理開始
        st.session_state.processing = True
        
        # UIプレースホルダー
        ui_placeholder = st.empty()
        
        with ui_placeholder.container():
            # バッチ数の計算
            total_batches = math.ceil(len(uploaded_files) / AppConfig.BATCH_SIZE)
            
            # プログレスバーの初期化
            progress_bar = st.progress(0, text="分析の準備をしています...")
            status_container = st.container()
            
            final_report_data = []
            error_count = 0
            
            try:
                # 各バッチを処理
                for batch_idx in range(0, len(uploaded_files), AppConfig.BATCH_SIZE):
                    current_batch_num = (batch_idx // AppConfig.BATCH_SIZE) + 1
                    
                    # プログレス更新
                    progress = batch_idx / len(uploaded_files)
                    progress_text = f"写真を分析中... (バッチ {current_batch_num}/{total_batches})"
                    progress_bar.progress(progress, text=progress_text)
                    
                    # バッチの準備
                    file_batch = uploaded_files[batch_idx:batch_idx + AppConfig.BATCH_SIZE]
                    filenames = [f.name for f in file_batch]
                    
                    # ステータス表示
                    with status_container:
                        st.info(f"分析中: {', '.join(filenames[:3])}{'...' if len(filenames) > 3 else ''}")
                    
                    # プロンプト生成
                    prompt = AIProcessor.create_report_prompt(filenames)
                    
                    # AI分析実行
                    response_text = AIProcessor.generate_ai_report(model, file_batch, prompt)
                    
                    if response_text:
                        # JSON解析
                        batch_report_data = AIProcessor.parse_json_response(response_text)
                        
                        if batch_report_data:
                            final_report_data.extend(batch_report_data)
                            logger.info(f"Successfully processed batch {current_batch_num}")
                        else:
                            error_count += 1
                            st.error(f"バッチ {current_batch_num} の解析でエラーが発生しました")
                    else:
                        error_count += 1
                        logger.error(f"Failed to get AI response for batch {current_batch_num}")
                
                # 処理完了
                progress_bar.progress(1.0, text="分析完了！")
                time.sleep(1)
                
                # エラーチェック
                if error_count > 0:
                    st.warning(f"{error_count}個のバッチで処理エラーが発生しました")
                
                if final_report_data:
                    # レポートデータの保存
                    st.session_state.files_dict = {f.name: f for f in uploaded_files}
                    st.session_state.report_payload = {
                        "title": report_title,
                        "date": survey_date.strftime('%Y年%m月%d日'),
                        "report_data": final_report_data,
                        "metadata": {
                            "created_at": date.today().isoformat(),
                            "total_images": len(uploaded_files),
                            "processed_images": len(final_report_data),
                            "error_count": error_count
                        }
                    }
                    
                    logger.info(f"Report created successfully: {len(final_report_data)} images processed")
                    
                    # 成功メッセージ
                    st.success(f"レポートの作成が完了しました！（{len(final_report_data)}枚を分析）")
                    time.sleep(1.5)
                else:
                    st.error("レポートの作成に失敗しました。もう一度お試しください。")
                    st.session_state.report_payload = None
                
            except Exception as e:
                # エラーハンドリング
                logger.error(f"Critical error during processing: {str(e)}\n{traceback.format_exc()}")
                st.error(f"処理中に予期しないエラーが発生しました: {str(e)}")
                st.session_state.report_payload = None
                
                # デバッグ情報（開発モード時のみ）
                if st.secrets.get("debug_mode", False):
                    with st.expander("デバッグ情報"):
                        st.code(traceback.format_exc())
                
            finally:
                # クリーンアップ
                st.session_state.processing = False
                ui_placeholder.empty()
                
                # メモリ解放
                gc.collect()
                
                # 画面更新
                st.rerun()

# ==============================================================================
# 10. アプリケーションのエントリーポイント
# ==============================================================================

if __name__ == "__main__":
    try:
        # ログレベルの設定（本番環境用）
        if not st.secrets.get("debug_mode", False):
            logging.getLogger().setLevel(logging.WARNING)
        
        # メインアプリケーションの実行
        main()
        
    except Exception as e:
        # 最上位のエラーハンドリング
        logger.critical(f"Application crashed: {str(e)}\n{traceback.format_exc()}")
        st.error("アプリケーションで重大なエラーが発生しました")
        st.error("ページを再読み込みしてください")
        
        # デバッグモードの場合は詳細を表示
        if st.secrets.get("debug_mode", False):
            st.exception(e)
