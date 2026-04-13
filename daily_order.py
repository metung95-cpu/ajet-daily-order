import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

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
st.title("🥩 에이젯 실시간 발주 관리")
st.sidebar.success(f"현재 접속: AZ 관리자")
if st.sidebar.button("로그아웃"):
    st.session_state["logged_in"] = False
    st.rerun()

raw_df = load_order_data()

if not raw_df.empty:
    if 'confirmed_indices' not in st.session_state:
        st.session_state['confirmed_indices'] = set()

    tab1, tab2, tab3 = st.tabs(["📦 출고 예정", "✅ 출고 확정", "📊 품목별 발주수량"])

    # 컬럼 정의 (시트 이름 기준)
    date_col = next((c for c in raw_df.columns if '날짜' in c or '일자' in c or '일' in c), "날짜")
    item_col = "품명 브랜드 등급 EST"
    qty_col = "수량(BOX)"
    manager_col = "담당자"
    client_col = "거래처명"
    time_col = "시간"

    # 표시할 컬럼 순서 (요청 사항 반영)
    display_order = [date_col, client_col, manager_col, item_col, qty_col, time_col]
    # 실제 존재하는 컬럼만 필터링
    actual_display_cols = [c for c in display_order if c in raw_df.columns]

    with tab1:
        st.subheader("미출고 발주 건 (날짜 필터 및 확정 처리)")
        
        # 날짜 필터 (내림차순 정렬)
        if date_col in raw_df.columns:
            unique_dates = sorted([d for d in raw_df[date_col].unique() if str(d).strip() != ''], reverse=True)
            selected_date = st.selectbox("📅 조회할 날짜 선택 (최신순)", ["전체 보기"] + unique_dates)
            
            pending_df = raw_df.copy()
            if selected_date != "전체 보기":
                pending_df = pending_df[pending_df[date_col] == selected_date]
        else:
            pending_df = raw_df.copy()

        # 이미 확정된 데이터 제외 및 요청 순서로 정렬
        pending_df = pending_df[~pending_df.index.isin(st.session_state['confirmed_indices'])]
        if item_col in pending_df.columns:
            pending_df = pending_df.sort_values(by=item_col)
        
        if not pending_df.empty:
            # 필요한 열만 추출 + 마지막에 체크박스용 열 추가
            pending_view = pending_df[actual_display_cols].copy()
            pending_view["👉 확정"] = False 

            dynamic_height = int((len(pending_view) + 1) * 36) + 3

            # 데이터 에디터 출력
            edited_df = st.data_editor(
                pending_view,
                column_config={"👉 확정": st.column_config.CheckboxColumn("출고완료", width="medium", default=False)},
                disabled=actual_display_cols,
                hide_index=True,
                use_container_width=True,
                height=dynamic_height
            )

            # 체크된 항목 처리
            confirmed_now = edited_df[edited_df["👉 확정"] == True].index
            if len(confirmed_now) > 0:
                # 뷰어의 인덱스와 원본 인덱스 매칭을 위해 실제 index 값 저장
                original_indices = pending_df.index[confirmed_now]
                st.session_state['confirmed_indices'].update(original_indices)
                st.toast(f"{len(confirmed_now)}건 출고 확정 완료!")
                time.sleep(0.5)
                st.rerun()
        else:
            st.info("현재 예정된 출고 건이 없습니다.")

    with tab2:
        st.subheader("출고 확정 내역")
        confirmed_df = raw_df[raw_df.index.isin(st.session_state['confirmed_indices'])]
        if not confirmed_df.empty:
            conf_view = confirmed_df[actual_display_cols]
            conf_dynamic_height = int((len(conf_view) + 1) * 36) + 3
            st.dataframe(conf_view, use_container_width=True, hide_index=True, height=conf_dynamic_height)
            if st.button("확정 내역 초기화"):
                st.session_state['confirmed_indices'] = set()
                st.rerun()
        else:
            st.write("확정된 내역이 없습니다.")

    with tab3:
        st.subheader("현재 출고 예정 품목별 총수량 (박스 합계)")
        # 전체 데이터 중 미확정 건만 필터링
        all_pending = raw_df[~raw_df.index.isin(st.session_state['confirmed_indices'])]
        
        if not all_pending.empty:
            # 시트의 실제 컬럼명 사용 (C열: 품명..., D열: 수량...)
            if qty_col in all_pending.columns and item_col in all_pending.columns:
                summary_df = all_pending.copy()
                # 수량 데이터를 숫자로 변환 (에러 방지)
                summary_df[qty_col] = pd.to_numeric(summary_df[qty_col].str.replace(',', ''), errors='coerce').fillna(0)
                
                # 품목별 합계 계산
                summary = summary_df.groupby(item_col)[qty_col].sum().reset_index()
                summary.columns = ['품목 (브랜드/등급/EST)', '출고예정 총수량(BOX)']
                
                # 수량이 있는 것만 표시 및 품목명 정렬
                summary = summary[summary['출고예정 총수량(BOX)'] > 0].sort_values('품목 (브랜드/등급/EST)')
                
                st.table(summary)
            else:
                st.warning(f"시트에서 '{item_col}' 또는 '{qty_col}' 컬럼을 찾을 수 없습니다. 컬럼명을 확인해 주세요.")
        else:
            st.write("집계할 예정 데이터가 없습니다.")

else:
    st.info("시트에 데이터가 없거나 불러오는 중입니다. 공유 권한을 확인해 보세요!")
