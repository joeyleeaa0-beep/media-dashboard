import streamlit as st
import pandas as pd
import requests
import plotly.express as px

st.set_page_config(page_title="新媒体数据看板", page_icon="📊", layout="wide")

APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]

APP_TOKEN_MEDIA = "A5iubfchuaOg6hsROvjcB4n1n9e"
TABLE_MEDIA = "tbl6qkkTey5NvSLl"

CITY_TABLES = {
    "深圳": "tbl46kSq4zHnoSfw",
    "上海": "tbl70UMMFEY0urht",
    "成都": "tbl4vrPA4DXL8lKJ",
    "天津": "tbl5EIkE87u80p2c",
}

MONTHS = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"]

@st.cache_data(ttl=300)
def get_token():
    res = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET}
    )
    return res.json().get("tenant_access_token")

def parse_field(val):
    if val is None:
        return None
    if isinstance(val, list):
        parts = []
        for v in val:
            if isinstance(v, dict):
                parts.append(v.get("text", v.get("name", str(v))))
            else:
                parts.append(str(v))
        return ", ".join(parts)
    if isinstance(val, dict):
        return val.get("text", val.get("name", str(val)))
    return val

@st.cache_data(ttl=300)
def fetch_table(app_token, table_id):
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    page_token = None
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        res = requests.get(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            headers=headers, params=params
        ).json()
        for item in res.get("data", {}).get("items", []):
            records.append({k: parse_field(v) for k, v in item.get("fields", {}).items()})
        if not res.get("data", {}).get("has_more"):
            break
        page_token = res["data"].get("page_token")
    return pd.DataFrame(records)

def to_num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)

def make_col(m, type_):
    num = m.replace("月", "").strip()
    if len(num) == 2:
        return f"{num}月：{type_}"
    else:
        return f"{num} 月：{type_}"

def get_city_metrics(city, month):
    if city not in city_dfs:
        return 0, 0, 0, 0
    cdf = city_dfs[city]
    if cdf.empty:
        return 0, 0, 0, 0

    daodian = 0
    chengjiao = 0
    xiaoshou = 0
    shougou = 0

    for _, row in cdf.iterrows():
        cat = str(row.get("线索分类|月份（1）", ""))
        if month == "全部月份":
            months_list = MONTHS
        else:
            months_list = [month]

        for m in months_list:
            sale_col = make_col(m, "销售")
            buy_col = make_col(m, "收购")
            val_sale = to_num(pd.Series([row.get(sale_col, 0)])).sum()
            val_buy = to_num(pd.Series([row.get(buy_col, 0)])).sum()

            if "总到店量" in cat:
                daodian += val_sale + val_buy
                xiaoshou += val_sale
                shougou += val_buy
            if "总成交量" in cat:
                chengjiao += val_sale + val_buy

    return daodian, chengjiao, xiaoshou, shougou

# ── 加载数据 ──
with st.spinner("正在加载数据..."):
    df_media = fetch_table(APP_TOKEN_MEDIA, TABLE_MEDIA)
    city_dfs = {}
    for city, tid in CITY_TABLES.items():
        city_dfs[city] = fetch_table(APP_TOKEN_MEDIA, tid)

# ── 侧边栏筛选 ──
st.sidebar.header("🔍 筛选条件")
cities = ["全部城市"] + list(CITY_TABLES.keys())
sel_city = st.sidebar.selectbox("筛选城市", cities)
months_opts = ["全部月份"] + MONTHS
sel_month = st.sidebar.selectbox("筛选月份", months_opts)

# ── 处理投放数据（只取合计行）──
df = df_media.copy()
if "渠道|平台" in df.columns:
    df = df[df["渠道|平台"].astype(str).str.contains("合计")]
if "地区" in df.columns and sel_city != "全部城市":
    df = df[df["地区"].astype(str) == sel_city]
if "月份" in df.columns and sel_month != "全部月份":
    df = df[df["月份"].astype(str) == sel_month]

total_spend = to_num(df["投放金额"]).sum() if "投放金额" in df.columns else 0
total_keizi = 0
for col in df.columns:
    if "客资" in col:
        total_keizi = to_num(df[col]).sum()
        break

# ── 处理线索数据 ──
if sel_city == "全部城市":
    total_daodian = 0
    total_chengjiao = 0
    total_xiaoshou = 0
    total_shougou = 0
    for city in CITY_TABLES.keys():
        d, c, x, s = get_city_metrics(city, sel_month)
        total_daodian += d
        total_chengjiao += c
        total_xiaoshou += x
        total_shougou += s
else:
    total_daodian, total_chengjiao, total_xiaoshou, total_shougou = get_city_metrics(sel_city, sel_month)

# ── 计算派生指标 ──
daodian_rate = (total_daodian / total_keizi * 100) if total_keizi > 0 else 0
chengjiao_rate = (total_chengjiao / total_keizi * 100) if total_keizi > 0 else 0
keizi_cost = (total_spend / total_keizi) if total_keizi > 0 else 0
daodian_cost = (total_spend / total_daodian) if total_daodian > 0 else 0
chengjiao_cost = (total_spend / total_chengjiao) if total_chengjiao > 0 else 0

# ── 核心指标 ──
st.title("📊 新媒体数据看板")
st.caption(f"城市：{sel_city} ｜ 月份：{sel_month}")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("总投放金额", f"¥{total_spend:,.0f}")
col2.metric("总客资量", f"{int(total_keizi):,}")
col3.metric("总到店量", f"{int(total_daodian):,}")
col4.metric("总成交量", f"{int(total_chengjiao):,}")
col5.metric("销售总量", f"{int(total_xiaoshou):,}")

col6, col7, col8, col9, col10 = st.columns(5)
col6.metric("收购总量", f"{int(total_shougou):,}")
col7.metric("总到店率", f"{daodian_rate:.2f}%", help="总到店量 / 客资量")
col8.metric("总成交率", f"{chengjiao_rate:.2f}%", help="总成交量 / 客资量")
col9.metric("客资成本", f"¥{keizi_cost:.2f}", help="投放金额 / 客资量")
col10.metric("成交成本", f"¥{chengjiao_cost:.2f}", help="投放金额 / 成交量")

st.divider()

# ── Tab ──
tab1, tab2, tab3, tab4 = st.tabs(["📊 大盘数据", "🏙️ 分城市数据", "📈 大盘趋势", "🏙️ 各城市趋势"])

with tab1:
    st.subheader("渠道投放明细")
    if not df_media.empty:
        df_show = df_media.copy()
        if "渠道|平台" in df_show.columns:
            df_show = df_show[df_show["渠道|平台"].astype(str).str.contains("合计")]
        if sel_city != "全部城市" and "地区" in df_show.columns:
            df_show = df_show[df_show["地区"].astype(str) == sel_city]
        if sel_month != "全部月份" and "月份" in df_show.columns:
            df_show = df_show[df_show["月份"].astype(str) == sel_month]
        cols_show = [c for c in ["地区", "月份", "渠道|平台", "投放金额"] if c in df_show.columns]
        for col in df_show.columns:
            if "客资" in col and col not in cols_show:
                cols_show.append(col)
        cols_show += [c for c in ["总成交量", "销售量", "收购量"] if c in df_show.columns]
        st.dataframe(df_show[cols_show].dropna(axis=1, how='all'), use_container_width=True)

with tab2:
    st.subheader("分城市经营对比")
    city_data = []
    for city in CITY_TABLES.keys():
        city_df = df_media[df_media["地区"].astype(str) == city].copy() if "地区" in df_media.columns else pd.DataFrame()
        if "渠道|平台" in city_df.columns:
            city_df = city_df[city_df["渠道|平台"].astype(str).str.contains("合计")]
        if sel_month != "全部月份" and "月份" in city_df.columns:
            city_df = city_df[city_df["月份"].astype(str) == sel_month]
        spend = to_num(city_df["投放金额"]).sum() if "投放金额" in city_df.columns else 0
        keizi = 0
        for col in city_df.columns:
            if "客资" in col:
                keizi = to_num(city_df[col]).sum()
                break
        d, c, x, s = get_city_metrics(city, sel_month)
        city_data.append({
            "城市": city,
            "客资量": int(keizi),
            "总到店量": int(d),
            "总成交量": int(c),
            "客资成交率": f"{(c/keizi*100):.2f}%" if keizi > 0 else "0%",
            "到店成交率": f"{(c/d*100):.2f}%" if d > 0 else "0%",
            "客资成本": f"¥{(spend/keizi):.2f}" if keizi > 0 else "N/A",
            "到店成本": f"¥{(spend/d):.2f}" if d > 0 else "N/A",
            "成交成本": f"¥{(spend/c):.2f}" if c > 0 else "N/A",
        })
    st.dataframe(pd.DataFrame(city_data), use_container_width=True, hide_index=True)

    city_df_plot = pd.DataFrame(city_data)
    ca, cb, cc = st.columns(3)
    with ca:
        fig = px.bar(city_df_plot, x="城市", y="客资量", title="各城市客资量", color="城市")
        st.plotly_chart(fig, use_container_width=True)
    with cb:
        fig2 = px.bar(city_df_plot, x="城市", y="总到店量", title="各城市到店量", color="城市")
        st.plotly_chart(fig2, use_container_width=True)
    with cc:
        fig3 = px.bar(city_df_plot, x="城市", y="总成交量", title="各城市成交量", color="城市")
        st.plotly_chart(fig3, use_container_width=True)

with tab3:
    st.subheader("大盘月度趋势")
    trend_df = df_media.copy()
    if "渠道|平台" in trend_df.columns:
        trend_df = trend_df[trend_df["渠道|平台"].astype(str).str.contains("合计")]
    if sel_city != "全部城市" and "地区" in trend_df.columns:
        trend_df = trend_df[trend_df["地区"].astype(str) == sel_city]
    keizi_col = next((c for c in trend_df.columns if "客资" in c), None)
    if "月份" in trend_df.columns and keizi_col:
        month_trend = trend_df.groupby("月份").agg(
            投放金额=("投放金额", lambda x: to_num(x).sum()),
            客资量=(keizi_col, lambda x: to_num(x).sum()),
        ).reset_index()
        month_trend["月份"] = pd.Categorical(month_trend["月份"], categories=MONTHS, ordered=True)
        month_trend = month_trend.sort_values("月份")
        fig4 = px.line(month_trend, x="月份", y=["投放金额", "客资量"],
                       title="月度投放与客资趋势", markers=True)
        st.plotly_chart(fig4, use_container_width=True)

with tab4:
    st.subheader("各城市月度趋势")
    trend_city = df_media.copy()
    if "渠道|平台" in trend_city.columns:
        trend_city = trend_city[trend_city["渠道|平台"].astype(str).str.contains("合计")]
    keizi_col2 = next((c for c in trend_city.columns if "客资" in c), None)
    if "月份" in trend_city.columns and "地区" in trend_city.columns and keizi_col2:
        city_trend = trend_city.groupby(["地区", "月份"]).agg(
            客资量=(keizi_col2, lambda x: to_num(x).sum()),
            投放金额=("投放金额", lambda x: to_num(x).sum()),
        ).reset_index()
        city_trend["月份"] = pd.Categorical(city_trend["月份"], categories=MONTHS, ordered=True)
        city_trend = city_trend.sort_values("月份")
        fig5 = px.line(city_trend, x="月份", y="客资量", color="地区",
                       title="各城市月度客资趋势", markers=True)
        st.plotly_chart(fig5, use_container_width=True)
        fig6 = px.line(city_trend, x="月份", y="投放金额", color="地区",
                       title="各城市月度投放趋势", markers=True)
        st.plotly_chart(fig6, use_container_width=True)
