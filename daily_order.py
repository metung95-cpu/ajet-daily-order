import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# ------------------------------------------------------------------
# 1. 기본 설정 및 보안 (로그인)
# ------------------------------------------------------------------
st.set_page_config(page_title="에이젯 발주 관리 시스템", page_icon="🥩", layout="wide")

# 로그인 상태 확인 함수
def check_login():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        st.title("🔒 에이젯 시스템 접속")
        with st.form("login_form"):
            user_id = st.text_input("아이디 (ID)")
            user_pw = st.text_input("비밀번호 (PW)", type="password")
            submitted = st.form_submit_button("로그인")
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
        
        # 탭 탐색 (4월발주)
        all_sheets = doc.worksheets()
        target_worksheet = next((s for s in all_sheets if '4월' in s.title and '발주' in s.title), doc.get_worksheet(0))
        
        data = target_worksheet.get_all_values()
        if not data or len(data) < 1: return pd.DataFrame()
            
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = df.columns.str.strip()
        df = df.loc[:, df.columns != '']
        
        # 데이터 클렌징: 상품명으로 정렬
        if '상품명' in df.columns:
            df = df.sort_values(by='상품명')
        elif '품목' in df.columns:
            df = df.sort_values(by='품목')
            
        return df
    except Exception as e:
        st.error(f"🚨 데이터 로드 실패: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 3. 메인 로직 및 탭 구성
# ------------------------------------------------------------------
st.title("🥩 에이젯 실시간 발주 관리")
st.sidebar.success(f"현재 접속: AZ 관리자")
if st.sidebar.button("로그아웃"):
    st.session_state["logged_in"] = False
    st.rerun()

# 원본 데이터 로드
raw_df = load_order_data()

if not raw_df.empty:
    # 체크박스 상태 관리를 위해 세션 스테이트 초기화
    if 'confirmed_indices' not in st.session_state:
        st.session_state['confirmed_indices'] = set()

    # 탭 생성
    tab1, tab2, tab3 = st.tabs(["📦 출고 예정", "✅ 출고 확정", "📊 품목별 발주수량"])

    with tab1:
        st.subheader("미출고 발주 건 (체크 시 확정으로 이동)")
        # 확정되지 않은 데이터만 필터링
        pending_df = raw_df.copy()
        pending_df = pending_df[~pending_df.index.isin(st.session_state['confirmed_indices'])]
        
        if not pending_df.empty:
            # 체크박스 컬럼 추가를 위해 데이터 편집 가능 모드(st.data_editor) 사용
            # height=None으로 설정하여 전체 행이 보이도록 처리
            edited_df = st.data_editor(
                pending_df.assign(확정=False),
                column_config={"확정": st.column_config.CheckboxColumn("출고확정", default=False)},
                disabled=[col for col in pending_df.columns],
                hide_index=True,
                use_container_width=True,
                height=None 
            )

            # 체크된 항목 찾기
            confirmed_now = edited_df[edited_df['확정'] == True].index
            if len(confirmed_now) > 0:
                st.session_state['confirmed_indices'].update(confirmed_now)
                st.toast(f"{len(confirmed_now)}건이 출고 확정 탭으로 이동되었습니다.")
                time.sleep(0.5)
                st.rerun()
        else:
            st.info("현재 예정된 출고 건이 없습니다.")

    with tab2:
        st.subheader("출고 확정 내역")
        confirmed_df = raw_df[raw_df.index.isin(st.session_state['confirmed_indices'])]
        if not confirmed_df.empty:
            # 확정 탭도 전체 스크롤을 위해 height=None
            st.dataframe(confirmed_df, use_container_width=True, hide_index=True, height=None)
            if st.button("확정 내역 초기화"):
                st.session_state['confirmed_indices'] = set()
                st.rerun()
        else:
            st.write("확정된 내역이 없습니다.")

    with tab3:
        st.subheader("품목별 출고 예정 수량 합계")
        # 예정 리스트 기준 집계
        if not pending_df.empty:
            # 수량 컬럼 찾기 (숫자로 변환)
            qty_col = next((c for c in pending_df.columns if '수량' in c or '개수' in c), None)
            item_col = next((c for c in pending_df.columns if '상품명' in c or '품목' in c), None)

            if qty_col and item_col:
                summary_df = pending_df.copy()
                summary_df[qty_col] = pd.to_numeric(summary_df[qty_col], errors='coerce').fillna(0)
                summary = summary_df.groupby(item_col)[qty_col].sum().reset_index()
                summary.columns = ['품목명', '출고예정 총수량']
                st.table(summary) # 집계표는 깔끔하게 일반 테이블로 표시
            else:
                st.warning("수량 또는 품목 컬럼을 찾을 수 없어 집계가 불가능합니다.")
        else:
            st.write("집계할 데이터가 없습니다.")

else:
    st.info("시트에 데이터가 없거나 불러오는 중입니다.")
