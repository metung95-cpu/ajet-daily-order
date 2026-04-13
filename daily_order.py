import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ------------------------------------------------------------------
# 1. 기본 설정
# ------------------------------------------------------------------
st.set_page_config(page_title="일자별 발주 조회", page_icon="📅", layout="wide")

# ------------------------------------------------------------------
# 2. 구글 시트 연결 함수
# ------------------------------------------------------------------
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    # 이전 앱들과 동일하게 st.secrets["gcp_service_account"]를 사용합니다.
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return gspread.authorize(creds)

# ------------------------------------------------------------------
# 3. 데이터 로딩 (캐시 적용)
# ------------------------------------------------------------------
@st.cache_data(ttl=60) # 1분마다 최신 데이터로 갱신
def load_order_data():
    try:
        gc = get_gspread_client()
        # 요청하신 URL 그대로 연결
        sheet_url = 'https://docs.google.com/spreadsheets/d/1bhfGQDzqA_W54CnWyVEXr07Ms74Yy3d1PctlVbZSVzk/edit'
        doc = gc.open_by_url(sheet_url)
        worksheet = doc.worksheet('4월발주')
        
        # 데이터 가져오기
        data = worksheet.get_all_values()
        
        if not data:
            return pd.DataFrame()
            
        # 첫 번째 줄을 컬럼명으로 사용하여 데이터프레임 생성
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # 빈 열/행 정리
        df.columns = df.columns.str.strip()
        df = df.loc[:, df.columns != '']
        
        return df
        
    except Exception as e:
        st.error(f"🚨 데이터 로드 실패: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 4. 메인 화면 구성
# ------------------------------------------------------------------
st.title("📅 4월 발주 일자별 조회")
st.markdown("---")

df = load_order_data()

if not df.empty:
    # 💡 [중요] 구글 시트의 날짜가 들어있는 컬럼의 이름을 찾습니다.
    # 시트에 '날짜', '일자', '발주일' 이라는 단어가 들어간 컬럼을 자동 탐색합니다.
    date_col_candidates = [col for col in df.columns if '날짜' in col or '일자' in col or '일' in col]
    
    if date_col_candidates:
        date_col = date_col_candidates[0] # 첫 번째로 일치하는 컬럼 사용
        
        # 1. 드롭다운 필터 생성 (시트에 있는 고유한 날짜값만 추출)
        unique_dates = [d for d in df[date_col].unique() if str(d).strip() != '']
        # 혹시 모를 에러 방지를 위해 문자로 변환 후 오름차순 정렬
        sorted_dates = sorted(unique_dates, key=str) 
        
        st.subheader(f"🔍 조회할 {date_col}을 선택하세요")
        selected_date = st.selectbox("선택", ["전체 보기"] + sorted_dates)
        
        # 2. 데이터 필터링
        if selected_date != "전체 보기":
            filtered_df = df[df[date_col] == selected_date]
        else:
            filtered_df = df
            
        # 3. 결과 표시
        st.markdown(f"**총 {len(filtered_df)}건의 데이터가 있습니다.**")
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        
    else:
        st.warning("데이터에서 '날짜'나 '일자'라는 이름이 포함된 컬럼을 찾을 수 없습니다. 시트의 첫 번째 줄(헤더)을 확인해 주세요.")
        st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("데이터를 불러오는 중이거나 시트가 비어있습니다.")
