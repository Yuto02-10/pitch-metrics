import os
import glob
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# -----------------------------------------------------------------------------
# 1. ページ基本設定
# -----------------------------------------------------------------------------
st.set_page_config(page_title="プロ野球級 投手分析 & 攻略ダッシュボード", layout="wide")

# -----------------------------------------------------------------------------
# 2. データ読み込み・前処理関数
# -----------------------------------------------------------------------------
@st.cache_data
def load_all_data(folder_path="試合データ"):
    search_path = os.path.join(folder_path, "*.csv")
    file_paths = glob.glob(search_path)
    
    if not file_paths:
        return None
        
    df_list = []
    for path in file_paths:
        try:
            df_each = pd.read_csv(path, encoding='utf-8')
        except UnicodeDecodeError:
            df_each = pd.read_csv(path, encoding='cp932')

        df_each = df_each.dropna(subset=['PitchType', 'PitchLocation'])
        df_each['Date'] = pd.to_datetime(df_each['Date'], errors='coerce')
        df_each = df_each.dropna(subset=['Date'])
        df_each['PitchLocation'] = pd.to_numeric(df_each['PitchLocation'], errors='coerce')

        if 'Batter' in df_each.columns:
            df_each['Batter'] = df_each['Batter'].astype(str).str.replace(r'\s+', '', regex=True)
        if 'Pitcher' in df_each.columns:
            df_each['Pitcher'] = df_each['Pitcher'].astype(str).str.replace(r'\s+', '', regex=True)
            
        df_list.append(df_each)
        
    if not df_list:
        return None

    df_concat = pd.concat(df_list, ignore_index=True)
    
    # 指標用フラグ追加
    strike_results = ['見逃し', '空振り', 'インプレー', 'ファウル']
    df_concat['IsStrike'] = df_concat['PitchResult'].isin(strike_results)
    df_concat['IsWhiff'] = df_concat['PitchResult'] == '空振り'
    df_concat['InZone'] = df_concat['PitchLocation'].between(1, 9)
    df_concat['IsHit'] = df_concat['HitResult'].isin(['単打', '二塁打', '三塁打', '本塁打'])
    
    # カウント文字列生成
    df_concat['Count'] = df_concat['Ball'].astype(str) + "B-" + df_concat['Strike'].astype(str) + "S"
    
    return df_concat

# データロード
df_raw = load_all_data()

if df_raw is None or df_raw.empty:
    st.warning("「試合データ/」フォルダにCSVファイルを追加してください。")
    st.stop()

# -----------------------------------------------------------------------------
# 3. サイドバーの設定 (投手選択・期間1・期間2・フィルター)
# -----------------------------------------------------------------------------
st.sidebar.title("⚙️ 分析コントロール")

# 投手選択
pitcher_list = sorted(df_raw['Pitcher'].dropna().unique())
selected_pitcher = st.sidebar.selectbox("分析対象投手を選択", pitcher_list)

# 該当投手のデータ抽出
df_pitcher = df_raw[df_raw['Pitcher'] == selected_pitcher]

min_date = df_pitcher['Date'].min().date()
max_date = df_pitcher['Date'].max().date()

st.sidebar.markdown("---")
st.sidebar.subheader("📅 期間選択")

# 期間1（短期/直近分析用）
st.sidebar.write("**【期間1】直近・短期データ（基本分析用）**")
period1_start, period1_end = st.sidebar.date_input(
    "期間1 日付範囲",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
    key="p1"
)

# 期間2（長期/スカウティング・通算用）
st.sidebar.write("**【期間2】通算・長期データ（比較・狙い球算出用）**")
period2_start, period2_end = st.sidebar.date_input(
    "期間2 日付範囲",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
    key="p2"
)

# 日付フィルタリング
df_p1 = df_pitcher[(df_pitcher['Date'].dt.date >= period1_start) & (df_pitcher['Date'].dt.date <= period1_end)]
df_p2 = df_pitcher[(df_pitcher['Date'].dt.date >= period2_start) & (df_pitcher['Date'].dt.date <= period2_end)]

st.title(f"⚾ 投手分析ダッシュボード：{selected_pitcher} 投手")

if df_p1.empty:
    st.error("期間1に該当する投球データがありません。期間を変更してください。")
    st.stop()

# -----------------------------------------------------------------------------
# 4. メインエリア：タブ構成
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "📊 投手パフォーマンス概要 (期間1)",
    "🎯 カウント別 狙い球算出 (短期 vs 長期)",
    "🗺️ 対右・対左 コースヒートマップ"
])

# =============================================================================
# TAB 1: 投手パフォーマンス概要 (期間1ベース)
# =============================================================================
with tab1:
    st.subheader("📌 期間1 サマリー指標")
    
    # 4つの重要KPIカード
    k1, k2, k3, k4 = st.columns(4)
    total_p1 = len(df_p1)
    str_rate = (df_p1['IsStrike'].sum() / total_p1 * 100) if total_p1 > 0 else 0
    whiff_rate = (df_p1['IsWhiff'].sum() / total_p1 * 100) if total_p1 > 0 else 0
    hits_count = df_p1['IsHit'].sum()
    
    k1.metric("投球数 (期間1)", f"{total_p1} 球")
    k2.metric("ストライク率", f"{str_rate:.1f} %")
    k3.metric("空振り率", f"{whiff_rate:.1f} %")
    k4.metric("被安打数", f"{hits_count} 本")

    st.markdown("---")
    
    col_g1, col_g2 = st.columns(2)

    # 1. 球種の投球割合 (横棒グラフ)
    with col_g1:
        st.subheader("🥎 球種ごとの投球割合")
        p_counts = df_p1['PitchType'].value_counts(normalize=True) * 100
        df_p_counts = p_counts.reset_index()
        df_p_counts.columns = ['球種', '割合(%)']
        df_p_counts['割合(%)'] = df_p_counts['割合(%)'].round(1)

        fig_pitch = px.bar(
            df_p_counts,
            x='割合(%)',
            y='球種',
            orientation='h',
            text='割合(%)',
            color='球種',
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_pitch.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig_pitch.update_layout(yaxis=dict(autorange="reversed"), xaxis=dict(range=[0, 105]), showlegend=False, height=300)
        st.plotly_chart(fig_pitch, use_container_width=True)

    # 2. 打たれた打球の種類 (100% 積み上げ横棒グラフ)
    with col_g2:
        st.subheader("💥 打球種類 & 三振割合 (100% 累積)")
        
        # 打球分類ロジック
        categories = []
        infielder = ['投手', '捕手', '一塁手', '二塁手', '三塁手', '遊撃手']
        outfielder = ['左翼手', '中堅手', '右翼手']
        
        for idx, row in df_p1.iterrows():
            if row['KorBB'] in ['空振り三振', '見逃し三振']:
                categories.append('三振')
            elif pd.notna(row['HitType']):
                ht = str(row['HitType'])
                catch = str(row['Catch']) if pd.notna(row['Catch']) else ''
                if 'ゴロ' in ht:
                    categories.append('ゴロ')
                elif 'ライナー' in ht:
                    categories.append('ライナー')
                elif 'フライ' in ht or 'ポップ' in ht:
                    if any(pos in catch for pos in infielder):
                        categories.append('内野フライ')
                    else:
                        categories.append('外野フライ')
                        
        cat_counts = pd.Series(categories).value_counts()
        total_events = cat_counts.sum()
        
        if total_events > 0:
            target_cats = ['ゴロ', '内野フライ', '外野フライ', 'ライナー', '三振']
            cat_percentages = {c: round((cat_counts.get(c, 0) / total_events) * 100, 1) for c in target_cats}
            
            fig_batted = go.Figure()
            colors = {'ゴロ': '#2b5c8f', '内野フライ': '#d95f02', '外野フライ': '#7570b3', 'ライナー': '#e7298a', '三振': '#66a61e'}
            
            for cat in target_cats:
                val = cat_percentages[cat]
                fig_batted.add_trace(go.Bar(
                    y=['打球傾向'],
                    x=[val],
                    name=cat,
                    orientation='h',
                    marker=dict(color=colors[cat]),
                    text=f"{cat}<br>{val}%" if val > 5 else "",
                    textposition='inside',
                    insidetextanchor='middle'
                ))

            fig_batted.update_layout(
                barmode='stack',
                xaxis=dict(title='割合 (%)', range=[0, 100]),
                height=300,
                margin=dict(l=10, r=10, t=30, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_batted, use_container_width=True)
        else:
            st.info("期間1において、インプレー打球または三振のデータがありません。")

    st.markdown("---")
    
    # 3. 球種ごとの詳細データ（被打率、ストライク率、ゾーン内%）
    st.subheader("📋 球種別スタッツの詳細 (期間1)")
    
    res_list = []
    for pt in df_p1['PitchType'].dropna().unique():
        df_pt = df_p1[df_p1['PitchType'] == pt]
        n_pt = len(df_pt)
        
        str_pct = (df_pt['IsStrike'].sum() / n_pt) * 100
        zone_pct = (df_pt['InZone'].sum() / n_pt) * 100
        
        # 被打率計算
        hits = df_pt['IsHit'].sum()
        outs_on_hit = df_pt['HitResult'].isin(['アウト']).sum()
        so = df_pt['KorBB'].isin(['空振り三振', '見逃し三振']).sum()
        ab = hits + outs_on_hit + so
        avg = (hits / ab) if ab > 0 else 0.0
        
        res_list.append({
            '球種': pt,
            '投球数': n_pt,
            '投球割合 (%)': round(n_pt / total_p1 * 100, 1),
            'ストライク率 (%)': round(str_pct, 1),
            'ゾーン内% (%)': round(zone_pct, 1),
            '安打-打数': f"{hits}-{ab}",
            '被打率': f"{avg:.3f}" if ab > 0 else ".---"
        })
        
    df_stats = pd.DataFrame(res_list).sort_values(by='投球数', ascending=False)
    st.dataframe(df_stats, use_container_width=True, hide_index=True)


# =============================================================================
# TAB 2: カウント別 狙い球算出 (短期 vs 長期)
# =============================================================================
with tab2:
    st.subheader("🎯 カウント別 狙い球・配球パターン比較 (短期 vs 長期)")
    st.write("期間1(短期)の直近傾向と、期間2(長期)の通算配球パターンを比較し、各カウントでの相手の狙い球（投球確率の高い球種）を算出します。")

    # カウントリストの整理
    counts = ["0B-0S", "1B-0S", "2B-0S", "3B-0S", "0B-1S", "1B-1S", "2B-1S", "3B-1S", "0B-2S", "1B-2S", "2B-2S", "3B-2S"]
    
    scout_data = []
    
    for c in counts:
        p1_c = df_p1[df_p1['Count'] == c]
        p2_c = df_p2[df_p2['Count'] == c]
        
        # 期間1の最多球種
        if not p1_c.empty:
            p1_top = p1_c['PitchType'].value_counts().index[0]
            p1_pct = (p1_c['PitchType'].value_counts().iloc[0] / len(p1_c)) * 100
            p1_str = f"{p1_top} ({p1_pct:.0f}%)"
        else:
            p1_top, p1_pct, p1_str = "データなし", 0, "---"

        # 期間2の最多球種
        if not p2_c.empty:
            p2_top = p2_c['PitchType'].value_counts().index[0]
            p2_pct = (p2_c['PitchType'].value_counts().iloc[0] / len(p2_c)) * 100
            p2_str = f"{p2_top} ({p2_pct:.0f}%)"
        else:
            p2_top, p2_pct, p2_str = "データなし", 0, "---"

        # 狙い球アドバイス判定ロジック
        if p1_top != "データなし" and p1_top == p2_top:
            advice = f"🔥 狙い目: 【{p1_top}】 (一致度高)"
        elif p1_top != "データなし" and p1_pct >= 40:
            advice = f"⚡ 短期警戒: 【{p1_top}】 (直近で多用)"
        elif p2_top != "データなし" and p2_pct >= 40:
            advice = f"📊 長期傾向: 【{p2_top}】 (通算の本命)"
        else:
            advice = "⚖️ 配球分散 (絞り込み注意)"

        scout_data.append({
            "カウント": c,
            "期間1 (短期最多)": p1_str,
            "期間2 (長期最多)": p2_str,
            "狙い球判定・アドバイス": advice
        })

    df_scout = pd.DataFrame(scout_data)
    st.dataframe(df_scout, use_container_width=True, hide_index=True)


# =============================================================================
# TAB 3: 対右・対左 コースヒートマップ
# =============================================================================
with tab3:
    st.subheader("🗺️ ゾーン別ヒートマップ分析 (期間1)")
    
    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        target_batter_lr = st.radio("打者の左右", ["右打者", "左打者"], horizontal=True)
    with col_h2:
        metric_choice = st.radio("分析指標", ["ストライク奪取率 (%)", "インプレー時危険度 (被安打率 %)"], horizontal=True)
    with col_h3:
        all_pitch_types = ["すべて"] + list(df_p1['PitchType'].dropna().unique())
        selected_pt_map = st.selectbox("球種絞り込み", all_pitch_types)

    # フィルタリング
    lr_key = "右" if target_batter_lr == "右打者" else "左"
    df_hm = df_p1[df_p1['BatterLR'] == lr_key]
    
    if selected_pt_map != "すべて":
        df_hm = df_hm[df_hm['PitchType'] == selected_pt_map]

    # 3x3ストライクゾーン + 4角ボールゾーン (5x3 グリッド構築)
    # [11:左上,  1:上左,  2:上中,  3:上右, 12:右上]
    # [ ---  ,  4:中左,  5:真中,  6:中右,  ---  ]
    # [13:左下,  7:下左,  8:下中,  9:下右, 14:右下]
    
    grid_matrix = np.full((3, 5), np.nan)
    text_matrix = np.full((3, 5), "", dtype=object)
    
    pos_mapping = {
        11: (0, 0), 1: (0, 1), 2: (0, 2), 3: (0, 3), 12: (0, 4),
        4: (1, 1), 5: (1, 2), 6: (1, 3),
        13: (2, 0), 7: (2, 1), 8: (2, 2), 9: (2, 3), 14: (2, 4)
    }

    zone_names = {
        11: "外高(左)", 1: "高左", 2: "高中", 3: "高右", 12: "外高(右)",
        4: "中左", 5: "真中", 6: "中右",
        13: "外低(左)", 7: "低左", 8: "低中", 9: "低右", 14: "外低(右)"
    }

    for loc, (r, c) in pos_mapping.items():
        df_loc = df_hm[df_hm['PitchLocation'] == loc]
        n_loc = len(df_loc)
        
        if n_loc > 0:
            if metric_choice == "ストライク奪取率 (%)":
                val = (df_loc['IsStrike'].sum() / n_loc) * 100
            else: # インプレー時危険度
                hits = df_loc['IsHit'].sum()
                val = (hits / n_loc) * 100 if n_loc > 0 else 0
                
            grid_matrix[r, c] = round(val, 1)
            text_matrix[r, c] = f"{zone_names[loc]}<br>{val:.1f}%<br>({n_loc}球)"
        else:
            text_matrix[r, c] = f"{zone_names[loc]}<br>データ無"

    # 色調の選択（ストライク率は青系、危険度は赤系）
    colorscale = "Blues" if metric_choice == "ストライク奪取率 (%)" else "Reds"

    fig_hm = px.imshow(
        grid_matrix,
        x=['ボール(外)', '内/外', '真ん中', '外/内', 'ボール(外)'],
        y=['高め', '真ん中', '低め'],
        text_auto=False,
        color_continuous_scale=colorscale,
        aspect="auto"
    )
    
    fig_hm.update_traces(
        text=text_matrix,
        texttemplate="%{text}",
        hovertemplate="コース: %{x}-%{y}<br>値: %{z}%<extra></extra>"
    )
    
    fig_hm.update_layout(
        title=f"ゾーン別 {metric_choice} （捕手目線 / 対{target_batter_lr}）",
        height=450
    )

    st.plotly_chart(fig_hm, use_container_width=True)
