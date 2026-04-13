@st.cache_data(ttl=60)
def load_order_data():
    try:
        gc = get_gspread_client()
        
        # 1. URL 대신 시트 고유 ID(Key)를 사용합니다 (더 확실한 방법)
        # URL에서 /d/ 와 /edit 사이의 문자열이 Key입니다.
        sheet_key = '1bhfGQDzqA_W54CnWyVEXr07Ms74Yy3d1PctlVbZSVzk'
        doc = gc.open_by_key(sheet_key)
        
        # 2. 시트 이름을 찾을 때 '4월'이 포함된 탭을 자동으로 찾도록 보완합니다.
        # 이렇게 하면 '4월발주', '4월 발주', '4월발주 ' 모두 찾아낼 수 있습니다.
        all_sheets = doc.worksheets()
        target_worksheet = None
        
        for sheet in all_sheets:
            if '4월' in sheet.title and '발주' in sheet.title:
                target_worksheet = sheet
                break
        
        # 만약 자동 탐색에 실패하면 수동으로 지정한 이름을 시도합니다.
        if target_worksheet is None:
            target_worksheet = doc.worksheet('4월발주')
            
        # 데이터 가져오기
        data = target_worksheet.get_all_values()
        
        if not data or len(data) < 1:
            st.error("시트에 데이터가 없거나 헤더(첫 줄)가 존재하지 않습니다.")
            return pd.DataFrame()
            
        # 데이터프레임 생성 및 정리
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = df.columns.str.strip() # 컬럼명 양끝 공백 제거
        df = df.loc[:, df.columns != '']    # 이름 없는 컬럼 제거
        
        return df
        
    except Exception as e:
        # 구체적인 에러 메시지를 화면에 띄워 원인을 파악합니다.
        st.error(f"🚨 상세 에러 발생: {e}")
        return pd.DataFrame()
