import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import re

# ------------------------------------------------------------------
# 1. 기본 설정 및 보안 (로그인)
# ------------------------------------------------------------------
st.set_page_config(page_title="에이젯 발주 관리 시스템", page_icon="🥩", layout="wide")

def check_login():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        st.title("🔒 에이젯 시스템 접속")
        with st.form("login_form"):
            user_id = st.text_input("아이디 (ID)")
            user_pw = st.text_input("비밀번호 (PW)", type="password")
            submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)
            if submitted:
                if user_id == "AZ" and user_pw == "5835":
                    st.session_state["logged_in"] = True
                    st.success("인증되었습니다. 데이터를 불러옵니다...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("계정 정보가 일치하지 않습니다.")
        return False
    return True

if not check_login():
    st.stop()

# ------------------------------------------------------------------
# 2. 구글 시트 연결 및 데이터 로드
# ------------------------------------------------------------------
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=60)
def load_order_data():
    try:
        gc = get_gspread_client()
        sheet_key = '1bhfGQDzqA_W54CnWyVEXr07Ms74Yy3d1PctlVbZSVzk'
        doc = gc.open_by_key(sheet_key)
        all_sheets = doc.worksheets()
        target_worksheet = next((s for s in all_sheets if '4월' in s.title and '발주' in s.title), doc.get_worksheet(0))
        
        data = target_worksheet.get_all_values()
        if not data or len(data) < 1: return pd.DataFrame()
            
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = df.columns.str.strip()
        df = df.loc[:, df.columns != '']
        return df
    except Exception as e:
        st.error(f"🚨 데이터 로드 실패: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 3. 메인 로직 및 탭 구성
# ------------------------------------------------------------------
st.title("🥩 에이젯 발주관리(운영부)")
st.sidebar.success(f"현재 접속: AZ 관리자")
if st.sidebar.button("로그아웃"):
    st.session_state["logged_in"] = False
    st.rerun()

raw_df = load_order_data()

if not raw_df.empty:
    if 'confirmed_indices' not in st.session_state:
        st.session_state['confirmed_indices'] = set()

    # 컬럼 정의 (시트 기준)
    date_col = next((c for c in raw_df.columns if '날짜' in c or '일자' in c or '일' in c), "날짜")
    item_col = "품명 브랜드 등급 EST"
    qty_col = "수량(BOX)"
    manager_col = "담당자"
    client_col = "거래처명"
    time_col = "시간"

    # 품명이 공백인 데이터 제거
    if item_col in raw_df.columns:
        raw_df = raw_df[raw_df[item_col].astype(str).str.strip() != ""]

    tab1, tab2, tab3 = st.tabs(["📦 출고 예정", "✅ 출고 확정", "📊 수량 집계(품목/담당자)"])

    actual_display_cols = [c for c in [date_col, client_col, manager_col, item_col, qty_col, time_col] if c in raw_df.columns]

    def sort_dates(date_list):
        def parse_date(d):
            nums = re.findall(r'\d+', str(d))
            return tuple(map(int, nums)) if nums else (0, 0)
        return sorted(date_list, key=parse_date, reverse=True)

    with tab1:
        st.subheader("미출고 발주 건 (체크 시 확정 이동)")
        
        if date_col in raw_df.columns:
            u_dates = [d for d in raw_df[date_col].unique() if str(d).strip() != '']
            sorted_dates = sort_dates(u_dates)
            selected_date_t1 = st.selectbox("📅 조회 날짜 선택 (최신순)", ["전체 보기"] + sorted_dates, key="t1_date")
            
            pending_df = raw_df.copy()
            if selected_date_t1 != "전체 보기":
                pending_df = pending_df[pending_df[date_col] == selected_date_t1]
        else:
            pending_df = raw_df.copy()

        # 이미 확정된 데이터 제외
        pending_df = pending_df[~pending_df.index.isin(st.session_state['confirmed_indices'])]
        if item_col in pending_df.columns:
            pending_df = pending_df.sort_values(by=item_col)
        
        if not pending_df.empty:
            pending_view = pending_df[actual_display_cols].copy()
            pending_view["👉 확정"] = False 
            d_height = int((len(pending_view) + 1) * 35) + 10

            edited_df_t1 = st.data_editor(
                pending_view,
                column_config={"👉 확정": st.column_config.CheckboxColumn("출고완료", width="medium")},
                disabled=actual_display_cols,
                hide_index=True,
                use_container_width=True,
                height=d_height,
                key="editor_pending"
            )

            confirmed_now = edited_df_t1[edited_df_t1["👉 확정"] == True].index
            if len(confirmed_now) > 0:
                st.session_state['confirmed_indices'].update(confirmed_now)
                st.toast(f"{len(confirmed_now)}건 확정!")
                time.sleep(0.5)
                st.rerun()
        else:
            st.info("예정된 출고 건이 없습니다.")

    with tab2:
        st.subheader("출고 확정 내역 (체크 시 다시 예정으로 이동)")
        
        # 확정된 데이터만 필터링
        confirmed_df = raw_df[raw_df.index.isin(st.session_state['confirmed_indices'])].copy()
        
        if not confirmed_df.empty:
            if item_col in confirmed_df.columns:
                confirmed_df = confirmed_df.sort_values(by=item_col)
            
            conf_view = confirmed_df[actual_display_cols].copy()
            conf_view["👉 취소"] = False 
            c_height = int((len(conf_view) + 1) * 35) + 10
            
            edited_df_t2 = st.data_editor(
                conf_view,
                column_config={"👉 취소": st.column_config.CheckboxColumn("확정취소", width="medium")},
                disabled=actual_display_cols,
                hide_index=True,
                use_container_width=True,
                height=c_height,
                key="editor_confirmed"
            )
            
            canceled_now = edited_df_t2[edited_df_t2["👉 취소"] == True].index
            if len(canceled_now) > 0:
                st.session_state['confirmed_indices'].difference_update(canceled_now)
                st.toast(f"{len(canceled_now)}건 확정 취소!")
                time.sleep(0.5)
                st.rerun()
                
            if st.button("전체 내역 초기화"):
                st.session_state['confirmed_indices'] = set()
                st.rerun()
        else:
            st.write("확정 내역이 없습니다.")

    with tab3:
        st.subheader("예정 수량 집계")
        
        all_pending = raw_df[~raw_df.index.isin(st.session_state['confirmed_indices'])]
        
        if not all_pending.empty:
            # 날짜 선택 드롭다운
            if date_col in all_pending.columns:
                u_dates_t3 = [d for d in all_pending[date_col].unique() if str(d).strip() != '']
                sorted_dates_t3 = sort_dates(u_dates_t3)
                selected_date_t3 = st.selectbox("📅 집계 날짜 선택", ["전체 보기"] + sorted_dates_t3, key="t3_date")
                
                if selected_date_t3 != "전체 보기":
                    all_pending = all_pending[all_pending[date_col] == selected_date_t3]

            # 💡 집계 화면을 두 개의 열로 나눕니다.
            col1, col2 = st.columns(2)
            
            # --- 품목별 집계 (왼쪽) ---
            with col1:
                st.markdown("#### 🥩 품목별 수량")
                if qty_col in all_pending.columns and item_col in all_pending.columns:
                    summary_item_df = all_pending.copy()
                    summary_item_df[qty_col] = pd.to_numeric(summary_item_df[qty_col].str.replace(',', ''), errors='coerce').fillna(0)
                    summary_item = summary_item_df.groupby(item_col)[qty_col].sum().reset_index()
                    summary_item.columns = ['품목 (브랜드/등급/EST)', '합계(BOX)']
                    summary_item = summary_item[summary_item['합계(BOX)'] > 0].sort_values('품목 (브랜드/등급/EST)')
                    st.dataframe(summary_item, use_container_width=True, hide_index=True)
                else:
                    st.warning(f"컬럼 '{item_col}' 또는 '{qty_col}'을 찾을 수 없습니다.")

            # --- 담당자별 집계 (오른쪽) ---
            with col2:
                st.markdown("#### 👤 담당자별 수량")
                if qty_col in all_pending.columns and manager_col in all_pending.columns:
                    summary_manager_df = all_pending.copy()
                    summary_manager_df[qty_col] = pd.to_numeric(summary_manager_df[qty_col].str.replace(',', ''), errors='coerce').fillna(0)
                    summary_manager = summary_manager_df.groupby(manager_col)[qty_col].sum().reset_index()
                    summary_manager.columns = ['담당자', '합계(BOX)']
                    # 이름 없는(빈칸) 담당자 처리 및 0 초과 항목 필터링
                    summary_manager = summary_manager[(summary_manager['합계(BOX)'] > 0) & (summary_manager['담당자'].astype(str).str.strip() != "")]
                    summary_manager = summary_manager.sort_values('합계(BOX)', ascending=False) # 수량 많은 순 정렬
                    st.dataframe(summary_manager, use_container_width=True, hide_index=True)
                else:
                    st.warning(f"컬럼 '{manager_col}' 또는 '{qty_col}'을 찾을 수 없습니다.")

        else:
            st.write("집계할 데이터가 없습니다.")

else:
    st.info("데이터를 불러오는 중입니다.")
