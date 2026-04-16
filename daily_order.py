import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import re
import datetime

# ------------------------------------------------------------------
# 1. 기본 설정 및 보안 (로그인)
# ------------------------------------------------------------------
st.set_page_config(page_title="에이젯 발주 관리 시스템", page_icon="🥩", layout="wide")

# 8시간 유지되는 서버 메모리
@st.cache_resource
def get_app_state():
    return {
        "logged_in": False,
        "login_expire_time": 0,
        "confirmed_indices": set() # 확정 내역(고유 ID) 보관
    }

app_state = get_app_state()

def check_login():
    current_time = time.time()
    
    if app_state["logged_in"] and current_time > app_state["login_expire_time"]:
        app_state["logged_in"] = False
        app_state["confirmed_indices"].clear()

    if not app_state["logged_in"]:
        st.title("🔒 에이젯 시스템 접속")
        with st.form("login_form"):
            user_id = st.text_input("아이디 (ID)")
            user_pw = st.text_input("비밀번호 (PW)", type="password")
            submitted = st.form_submit_button("로그인", type="primary", use_container_width=True)
            if submitted:
                if user_id == "AZ" and user_pw == "5835":
                    app_state["logged_in"] = True
                    app_state["login_expire_time"] = current_time + (8 * 3600)
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
        
        item_col = "품명 브랜드 등급 EST"
        if item_col in df.columns:
            df[item_col] = df[item_col].astype(str).str.strip()
            df = df[~df[item_col].str.startswith(('냉', '.냉'))]
            df = df[df[item_col] != ""]
            
        qty_col = "수량(BOX)"
        if qty_col in df.columns:
            df[qty_col] = pd.to_numeric(df[qty_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0).astype(int)
            df = df[df[qty_col] > 0]
            
        # 고유 식별자(UID) 생성 로직 (확정 풀림 방지)
        uid_cols = [c for c in df.columns if c in ['날짜', '시간', '거래처명', '담당자', '품명 브랜드 등급 EST', '수량(BOX)']]
        df['UID'] = df[uid_cols].astype(str).agg('_'.join, axis=1)
        df['UID'] = df['UID'] + "_" + df.groupby('UID').cumcount().astype(str)
        df.set_index('UID', inplace=True)
            
        return df
    except Exception as e:
        st.error(f"🚨 데이터 로드 실패: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 3. 메인 로직 및 탭 구성
# ------------------------------------------------------------------
st.title("🥩 AZ 발주확인(운영부)")

st.sidebar.success(f"현재 접속: AZ 관리자")
remaining_seconds = int(app_state["login_expire_time"] - time.time())
hours, remainder = divmod(remaining_seconds, 3600)
minutes, _ = divmod(remainder, 60)
st.sidebar.info(f"⏳ 자동 로그아웃까지:\n\n**{hours}시간 {minutes}분 남음**")

if st.sidebar.button("수동 로그아웃"):
    app_state["logged_in"] = False
    st.rerun()

raw_df = load_order_data()

if not raw_df.empty:
    # 컬럼 동적 찾기
    date_col = next((c for c in raw_df.columns if '날짜' in c or '일자' in c or '일' in c), "날짜")
    item_col = "품명 브랜드 등급 EST"
    qty_col = "수량(BOX)"
    manager_col = "담당자"
    client_col = "거래처명"
    time_col = "시간"
    
    # 💡 [핵심 추가] 비고 열과 추가 열 찾기
    note_col = next((c for c in raw_df.columns if '비고' in c), "비고(이력,수기,취소)")
    add_col = next((c for c in raw_df.columns if '추가' in c), "추가")

    tab1, tab2, tab3 = st.tabs(["📦 출고 예정", "✅ 출고 확정", "📊 품목/담당자별 수량 현황"])

    # 💡 화면에 표시할 컬럼 목록에 비고, 추가 열 포함 (보기 편한 순서로 배치)
    actual_display_cols = [c for c in [date_col, time_col, client_col, manager_col, item_col, qty_col, note_col, add_col] if c in raw_df.columns]

    # 💡 [핵심 추가] 글자가 잘리지 않도록 컬럼별로 넉넉한 넓이 강제 지정
    base_col_config = {
        item_col: st.column_config.TextColumn(width="large"),
        note_col: st.column_config.TextColumn(width="large"),
        add_col: st.column_config.TextColumn(width="medium"),
        client_col: st.column_config.TextColumn(width="medium")
    }

    def sort_dates(date_list):
        def parse_date(d):
            nums = re.findall(r'\d+', str(d))
            return tuple(map(int, nums)) if nums else (0, 0)
        return sorted(date_list, key=parse_date, reverse=True)

    today = datetime.datetime.now()
    today_m_d = f"{today.month}. {today.day}"
    today_d = str(today.day)

    # 탭 1: 출고 예정
    with tab1:
        if date_col in raw_df.columns:
            u_dates = [d for d in raw_df[date_col].unique() if str(d).strip() != '']
            sorted_dates = sort_dates(u_dates)
            
            default_index = 0
            for i, d in enumerate(sorted_dates):
                if today_m_d in str(d) or str(d).strip() == today_d:
                    default_index = i + 1
                    break
            
            selected_date_t1 = st.selectbox(
                "📅 조회 날짜 선택 (냉장 제외)", 
                ["전체 보기"] + sorted_dates, 
                index=default_index, 
                key="t1_date"
            )
            
            pending_df = raw_df.copy()
            if selected_date_t1 != "전체 보기":
                pending_df = pending_df[pending_df[date_col] == selected_date_t1]
        else:
            pending_df = raw_df.copy()

        pending_df = pending_df[~pending_df.index.isin(app_state['confirmed_indices'])]
        
        if item_col in pending_df.columns:
            sort_cols = [item_col]
            if client_col in pending_df.columns: sort_cols.append(client_col)
            pending_df = pending_df.sort_values(by=sort_cols)
        
        if not pending_df.empty:
            pending_view = pending_df[actual_display_cols].copy()
            pending_view["👉 확정"] = False 
            
            t1_height = int((len(pending_view) + 1) * 35) + 40
            
            # 확정 체크박스 설정 추가
            t1_config = base_col_config.copy()
            t1_config["👉 확정"] = st.column_config.CheckboxColumn("출고완료", width="small")

            edited_df_t1 = st.data_editor(
                pending_view,
                column_config=t1_config,
                disabled=actual_display_cols,
                hide_index=True,
                use_container_width=False, # 💡 화면에 억지로 맞추지 않고 내용 길이에 맞춰서 표가 시원하게 늘어납니다!
                height=t1_height, 
                key="editor_pending"
            )

            confirmed_now = edited_df_t1[edited_df_t1["👉 확정"] == True].index
            if len(confirmed_now) > 0:
                app_state['confirmed_indices'].update(confirmed_now)
                st.toast(f"{len(confirmed_now)}건 확정 완료!")
                time.sleep(0.5)
                st.rerun()
        else:
            st.info("선택한 날짜에 예정된 출고 건이 없습니다.")

    # 탭 2: 출고 확정
    with tab2:
        confirmed_df = raw_df[raw_df.index.isin(app_state['confirmed_indices'])].copy()
        if not confirmed_df.empty:
            if item_col in confirmed_df.columns:
                sort_cols = [item_col]
                if client_col in confirmed_df.columns: sort_cols.append(client_col)
                confirmed_df = confirmed_df.sort_values(by=sort_cols)
                
            conf_view = confirmed_df[actual_display_cols].copy()
            conf_view["👉 취소"] = False 
            
            t2_height = int((len(conf_view) + 1) * 35) + 40
            
            # 취소 체크박스 설정 추가
            t2_config = base_col_config.copy()
            t2_config["👉 취소"] = st.column_config.CheckboxColumn("확정취소", width="small")

            edited_df_t2 = st.data_editor(
                conf_view,
                column_config=t2_config,
                disabled=actual_display_cols,
                hide_index=True,
                use_container_width=False, # 💡 여기도 글자 길이에 맞춰 늘어남
                height=t2_height,
                key="editor_confirmed"
            )
            
            canceled_now = edited_df_t2[edited_df_t2["👉 취소"] == True].index
            if len(canceled_now) > 0:
                app_state['confirmed_indices'].difference_update(canceled_now)
                st.toast(f"{len(canceled_now)}건 확정 취소!")
                time.sleep(0.5)
                st.rerun()
                
            if st.button("전체 내역 초기화 (다시 예정으로)"):
                app_state['confirmed_indices'].clear()
                st.rerun()
        else:
            st.write("확정 내역이 없습니다.")

    # 탭 3: 집계 현황
    with tab3:
        all_pending = raw_df[~raw_df.index.isin(app_state['confirmed_indices'])]
        
        if not all_pending.empty:
            if date_col in all_pending.columns:
                u_dates_t3 = [d for d in all_pending[date_col].unique() if str(d).strip() != '']
                sorted_dates_t3 = sort_dates(u_dates_t3)
                
                default_index_t3 = 0
                for i, d in enumerate(sorted_dates_t3):
                    if today_m_d in str(d) or str(d).strip() == today_d:
                        default_index_t3 = i + 1
                        break

                selected_date_t3 = st.selectbox(
                    "📅 집계 날짜 선택", 
                    ["전체 보기"] + sorted_dates_t3, 
                    index=default_index_t3, 
                    key="t3_date"
                )
                if selected_date_t3 != "전체 보기":
                    all_pending = all_pending[all_pending[date_col] == selected_date_t3]

            if qty_col in all_pending.columns and item_col in all_pending.columns and manager_col in all_pending.columns:
                pivot_df = all_pending.copy()
                pivot_df[manager_col] = pivot_df[manager_col].replace('', '미지정').fillna('미지정')
                
                pivot_table = pd.pivot_table(
                    pivot_df, values=qty_col, index=item_col, columns=manager_col, aggfunc='sum', fill_value=0
                )
                
                pivot_table['총 합계'] = pivot_table.sum(axis=1)
                pivot_table = pivot_table.sort_values('총 합계', ascending=False)
                
                pivot_display = pivot_table.astype(int).astype(object).replace(0, "")
                pivot_display = pivot_display.reset_index()
                pivot_display.rename(columns={item_col: '품목 (브랜드/등급/EST)'}, inplace=True)

                st.markdown("---")
                
                t3_height = int((len(pivot_display) + 1) * 35) + 40
                
                # 💡 집계 현황도 품목 이름이 길면 넓게 보여주도록 설정
                st.dataframe(
                    pivot_display, 
                    use_container_width=False, 
                    column_config={'품목 (브랜드/등급/EST)': st.column_config.TextColumn(width="large")},
                    hide_index=True, 
                    height=t3_height
                )
            else:
                st.warning("집계 컬럼을 찾을 수 없습니다.")
        else:
            st.write("집계할 예정 데이터가 없습니다.")

else:
    st.info("냉동 품목 발주 내역이 없거나 데이터를 로딩 중입니다.")
