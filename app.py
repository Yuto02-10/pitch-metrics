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
# 2. データ読み込み & 前処理（堅牢版）
# -----------------------------------------------------------------------------
@st.cache_data
def load_all_data(folder_path="試合データ"):
    search_path = os.path.join(folder_path, "*.csv")
    file_paths = glob.glob(search_path)
    
    if not file_paths:
        return None
        
    df_list = []
    for path in file_paths:
        if os.path.getsize(path) == 0:
            continue
            
        try:
            try:
                df_each = pd.read_csv(path, encoding='utf-8')
            except UnicodeDecodeError:
                df_each = pd.read_csv(path, encoding='cp932')
        except (pd.errors.EmptyDataError, Exception):
            continue

        if 'PitchType' not in df_each.columns or 'PitchLocation' not in df_each.columns:
            continue

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
    df_concat['Count'] = df_concat['Ball'].astype(str) + "B-" + df_concat['Strike'].astype(str) + "S"
    
    return df_concat

    # 危険度スコア（打者利得 / 被打撃ダメージ）算出ロジック
    # -------------------------------------------------------------------------
    def calc_advanced_danger_score(row):
        korbb = str(row.get('KorBB', ''))
        pitch_res = str(row.get('PitchResult', ''))
        
        # 1. 三振 / 四死球の判定
        if '三振' in korbb:
            return -2.5  # 危険度：低 (投手加点 +2.5 の反転)
        if '四球' in korbb:
            return 4.0   # 危険度：高
        if pitch_res == '死球':
            return 3.0   # 危険度：高

        # 2. 単発投球結果の判定
        if pitch_res == '空振り': return -1.5
        if pitch_res == '見逃し': return -1.3
        if pitch_res == 'ファウル': return -0.7
        if pitch_res == 'ボール':   return 0.4

        # 3. インプレー時の判定
        if pitch_res == 'インプレー':
            hit_type = str(row.get('HitType', ''))
            hit_result = str(row.get('HitResult', ''))
            catch_pos = str(row.get('Catch', ''))
            infielders = ['投手', '捕手', '一塁手', '二塁手', '三塁手', '遊撃手']

            # アウト / データなしの場合 (危険度：低)
            if hit_result in ['アウト', 'nan', '犠打', '犠飛']:
                if 'フライ' in hit_type:
                    return -2.5 if any(pos in catch_pos for pos in infielders) else -1.8
                elif 'ゴロ' in hit_type:
                    return -2.0
                elif 'ライナー' in hit_type:
                    return -1.5
                else:
                    return -0.5

            # 安打・長打・エラーマトリックス (危険度：高)
            weight_matrix = {
                ('ゴロ', '単打'): 2.8,     ('ライナー', '単打'): 5.5,   ('フライ', '単打'): 4.7,
                ('ゴロ', '二塁打'): 6.3,   ('ライナー', '二塁打'): 8.0,  ('フライ', '二塁打'): 9.5,
                ('ゴロ', '三塁打'): 8.0,   ('ライナー', '三塁打'): 9.5,  ('フライ', '三塁打'): 11.0,
                ('ゴロ', '本塁打'): 4.5,   ('ライナー', '本塁打'): 20.0, ('フライ', '本塁打'): 16.0,
                ('ゴロ', 'エラー'): -2.5,  ('ライナー', 'エラー'): -1.5, ('フライ', 'エラー'): -1.0,
            }
            
            # 部分一致用マッピング処理
            for (ht, hr), val in weight_matrix.items():
                if ht in hit_type and hr in hit_result:
                    return val
                    
            return 0.0

        return 0.0

    df_concat['DangerScore'] = df_concat.apply(calc_advanced_danger_score, axis=1)
    df_concat['IsInPlay'] = df_concat['PitchResult'] == 'インプレー'

# データロード
df_raw = load_all_data()

if df_raw is None or df_raw.empty:
    st.warning("「試合データ/」フォルダに適切なCSVファイルを追加してください。")
    st.stop()

# -----------------------------------------------------------------------------
# 3. サイドバー (投手選択 & 期間設定)
# -----------------------------------------------------------------------------
st.sidebar.title("⚙️ 分析コントロール")

pitcher_list = sorted(df_raw['Pitcher'].dropna().unique())
selected_pitcher = st.sidebar.selectbox("分析対象投手を選択", pitcher_list)

df_pitcher = df_raw[df_raw['Pitcher'] == selected_pitcher]

min_date = df_pitcher['Date'].min().date()
max_date = df_pitcher['Date'].max().date()

st.sidebar.markdown("---")
st.sidebar.subheader("📅 期間選択")

st.sidebar.write("**【期間1】短期・直近データ（基本グラフ生成用）**")
period1_start, period1_end = st.sidebar.date_input(
    "期間1 範囲", value=(min_date, max_date), min_value=min_date, max_value=max_date, key="p1"
)

st.sidebar.write("**【期間2】長期・通算データ（狙い球算出用）**")
period2_start, period2_end = st.sidebar.date_input(
    "期間2 範囲", value=(min_date, max_date), min_value=min_date, max_value=max_date, key="p2"
)

df_p1 = df_pitcher[(df_pitcher['Date'].dt.date >= period1_start) & (df_pitcher['Date'].dt.date <= period1_end)]
df_p2 = df_pitcher[(df_pitcher['Date'].dt.date >= period2_start) & (df_pitcher['Date'].dt.date <= period2_end)]

st.title(f"⚾ 投手分析ダッシュボード：{selected_pitcher} 投手")

if df_p1.empty:
    st.error("期間1に該当する投球データがありません。サイドバーで期間を変更してください。")
    st.stop()

# -----------------------------------------------------------------------------
# 4. コース名称・マッピング定義関数（打者左右対応）
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# 4. コース名称・マッピング定義関数（コース番号表記版）
# -----------------------------------------------------------------------------
def get_zone_config():
    """
    コース番号のみを表示する5x3グリッド構成を返す
    """
    names = {
        1: "ゾーン1", 2: "ゾーン2", 3: "ゾーン3",
        4: "ゾーン4", 5: "ゾーン5", 6: "ゾーン6",
        7: "ゾーン7", 8: "ゾーン8", 9: "ゾーン9",
        11: "ゾーン11", 12: "ゾーン12",
        13: "ゾーン13", 14: "ゾーン14"
    }
    # 5x3グリッド位置 [行, 列]
    pos = {
        11: (0, 0), 1: (0, 1), 2: (0, 2), 3: (0, 3), 12: (0, 4),
        4: (1, 1), 5: (1, 2), 6: (1, 3),
        13: (2, 0), 7: (2, 1), 8: (2, 2), 9: (2, 3), 14: (2, 4)
    }
    x_labels = ['ボール(11/13)', '1 / 4 / 7', '2 / 5 / 8', '3 / 6 / 9', 'ボール(12/14)']
        
    return names, pos, x_labels

# -----------------------------------------------------------------------------
# 5. タブ構成
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "📊 投手パフォーマンス概要 (期間1)",
    "🎯 高度な狙い球・コース予測 (期間1 & 期間2)",
    "🗺️ コース別ヒートマップ (右・左打者視点)"
])

# =============================================================================
# TAB 1: 投手パフォーマンス概要 (期間1ベース)
# =============================================================================
with tab1:
    st.subheader("📌 期間1 サマリー指標")
    
    k1, k2, k3, k4 = st.columns(4)
    total_p1 = len(df_p1)
    str_rate = (df_p1['IsStrike'].sum() / total_p1 * 100) if total_p1 > 0 else 0
    whiff_rate = (df_p1['IsWhiff'].sum() / total_p1 * 100) if total_p1 > 0 else 0
    hits_count = df_p1['IsHit'].sum()
    
    k1.metric("総投球数 (期間1)", f"{total_p1} 球")
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
            df_p_counts, x='割合(%)', y='球種', orientation='h', text='割合(%)',
            color='球種', color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_pitch.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig_pitch.update_layout(yaxis=dict(autorange="reversed"), xaxis=dict(range=[0, 105]), showlegend=False, height=300)
        st.plotly_chart(fig_pitch, use_container_width=True)

    # 2. 打球種類 (100% 積み上げ横棒グラフ)
    with col_g2:
        st.subheader("💥 打球種類 & 三振割合 (合計100%)")
        
        categories = []
        infielder = ['投手', '捕手', '一塁手', '二塁手', '三塁手', '遊撃手']
        
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
                    y=['打球/三振傾向'], x=[val], name=cat, orientation='h',
                    marker=dict(color=colors[cat]),
                    text=f"{cat}<br>{val}%" if val > 4 else "",
                    textposition='inside', insidetextanchor='middle'
                ))

            fig_batted.update_layout(
                barmode='stack', xaxis=dict(title='割合 (%)', range=[0, 100]), height=300,
                margin=dict(l=10, r=10, t=30, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_batted, use_container_width=True)
        else:
            st.info("期間1で打球または三振のデータがありません。")

    st.markdown("---")
    
    # 3. 球種別詳細テーブル
    st.subheader("📋 球種別スタッツ (被打率・ストライク率・ゾーン内%)")
    
    res_list = []
    for pt in df_p1['PitchType'].dropna().unique():
        df_pt = df_p1[df_p1['PitchType'] == pt]
        n_pt = len(df_pt)
        
        str_pct = (df_pt['IsStrike'].sum() / n_pt) * 100
        zone_pct = (df_pt['InZone'].sum() / n_pt) * 100
        
        hits = df_pt['IsHit'].sum()
        outs_on_hit = df_pt['HitResult'].isin(['アウト']).sum()
        so = df_pt['KorBB'].isin(['空振り三振', '見逃し三振']).sum()
        ab = hits + outs_on_hit + so
        avg = (hits / ab) if ab > 0 else 0.0
        
        res_list.append({
            '球種': pt, '投球数': n_pt,
            '投球割合 (%)': round(n_pt / total_p1 * 100, 1),
            'ストライク率 (%)': round(str_pct, 1),
            'ゾーン内% (%)': round(zone_pct, 1),
            '安打-打数': f"{hits}-{ab}",
            '被打率': f"{avg:.3f}" if ab > 0 else ".---"
        })
        
    df_stats = pd.DataFrame(res_list).sort_values(by='投球数', ascending=False)
    st.dataframe(df_stats, use_container_width=True, hide_index=True)


# =============================================================================
# TAB 2: 高度な狙い球・コース予測 (期間1 & 期間2)
# =============================================================================
with tab2:
    st.subheader("🎯 カウント別 狙い球・コース予測（高度加重予測モデル）")
    st.write("直近の傾向（期間1: 重み1.5）と通算の配球パターン（期間2: 重み1.0）を統合し、カウントごとに**狙うべき球種と予測コース（第1〜第3候補）**を自動算出します。")

    target_lr_scout = st.radio("打者打席の選択", ["右打者", "左打者"], key="scout_lr", horizontal=True)
    lr_key = "右" if target_lr_scout == "右打者" else "左"
    
    zone_names_scout, _, _ = get_zone_config()
    
    counts = ["0B-0S", "1B-0S", "2B-0S", "3B-0S", "0B-1S", "1B-1S", "2B-1S", "3B-1S", "0B-2S", "1B-2S", "2B-2S", "3B-2S"]
    
    scout_rows = []
    
    for c in counts:
        p1_c = df_p1[(df_p1['Count'] == c) & (df_p1['BatterLR'] == lr_key)]
        p2_c = df_p2[(df_p2['Count'] == c) & (df_p2['BatterLR'] == lr_key)]
        
        # 加重スコアリング
        pitch_score = {}
        all_pitch_types = set(p1_c['PitchType'].unique()).union(set(p2_c['PitchType'].unique()))
        
        if not all_pitch_types:
            scout_rows.append({
                "カウント": c, "データ数": "0球",
                "🥇 第1候補 (球種 / 予測コース)": "データ不足",
                "🥈 第2候補": "---", "🥉 第3候補": "---"
            })
            continue

        n_p1 = len(p1_c)
        n_p2 = len(p2_c)
        
        for pt in all_pitch_types:
            ratio_p1 = (len(p1_c[p1_c['PitchType'] == pt]) / n_p1) if n_p1 > 0 else 0
            ratio_p2 = (len(p2_c[p2_c['PitchType'] == pt]) / n_p2) if n_p2 > 0 else 0
            # 直近データ(期間1)に1.5倍の重み付け
            score = (ratio_p1 * 1.5) + (ratio_p2 * 1.0)
            pitch_score[pt] = score

        # スコア上位でソート
        sorted_pitches = sorted(pitch_score.items(), key=lambda x: x[1], reverse=True)
        total_score = sum(pitch_score.values())

        # 候補ごとの文字列生成（第1〜第3候補）
        cand_strings = []
        for i in range(3):
            if i < len(sorted_pitches) and total_score > 0:
                pt, sc = sorted_pitches[i]
                prob = (sc / total_score) * 100
                
                # 最多投球コースの検出 (期間1+期間2統合)
                combined_c = pd.concat([p1_c[p1_c['PitchType'] == pt], p2_c[p2_c['PitchType'] == pt]])
                if not combined_c.empty and combined_c['PitchLocation'].notna().any():
                    top_loc = combined_c['PitchLocation'].mode().iloc[0]
                    course_str = zone_names_scout.get(int(top_loc), f"ゾーン{int(top_loc)}")
                else:
                    course_str = "コース不明"
                    
                cand_strings.append(f"**{pt}** ({prob:.0f}%) <br>📍 {course_str}")
            else:
                cand_strings.append("---")

        scout_rows.append({
            "カウント": c,
            "データ数": f"短期{n_p1}球 / 通算{n_p2}球",
            "🥇 第1候補 (球種 / 予測コース)": cand_strings[0],
            "🥈 第2候補": cand_strings[1],
            "🥉 第3候補": cand_strings[2]
        })

    df_scout_result = pd.DataFrame(scout_rows)
    st.write(f"### 💡 対 {target_lr_scout} 狙い球・コース予測一覧")
    st.write("※ **確率(%)**は予測モデルによる相対的な投球確率、**📍 コース**はその球種が最も集中しているゾーンを示します。")
    st.markdown(df_scout_result.to_html(escape=False, index=False), unsafe_allow_html=True)


# =============================================================================
# TAB 3: コース別ヒートマップ (期間1ベース)
# =============================================================================
with tab3:
    st.subheader("🗺️ コース別ヒートマップ (期間1)")
    
    # -------------------------------------------------------------------------
    # コントロールUI (打者打席 / 表示指標 / 球種絞り込み)
    # -------------------------------------------------------------------------
    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        target_batter_lr = st.radio("打者打席の選択", ["右打者", "左打者"], key="hm_lr", horizontal=True)
    with col_h2:
        metric_choice = st.radio(
            "表示指標", 
            ["ストライク奪取率 (%)", "インプレー時危険度 (被安打率 %)", "高度危険度スコア (平均)"], 
            key="hm_metric",
            horizontal=True
        )
    with col_h3:
        all_pitch_types = ["すべて"] + list(df_p1['PitchType'].dropna().unique())
        selected_pt_map = st.selectbox("球種絞り込み", all_pitch_types, key="hm_pt")

    # -------------------------------------------------------------------------
    # データのフィルタリング
    # -------------------------------------------------------------------------
    lr_key = "右" if target_batter_lr == "右打者" else "左"
    df_hm = df_p1[df_p1['BatterLR'] == lr_key]
    
    if selected_pt_map != "すべて":
        df_hm = df_hm[df_hm['PitchType'] == selected_pt_map]

    # コース番号・マッピング設定の取得 (ゾーン番号表示に統一)
    zone_names, pos_mapping, x_axis_labels = get_zone_config()

    # -------------------------------------------------------------------------
    # 5x3 グリッド行列の生成
    # -------------------------------------------------------------------------
    grid_matrix = np.full((3, 5), np.nan)
    text_matrix = np.full((3, 5), "", dtype=object)

    for loc, (r, c) in pos_mapping.items():
        df_loc = df_hm[df_hm['PitchLocation'] == loc]
        n_loc = len(df_loc)
        
        if n_loc > 0:
            if metric_choice == "ストライク奪取率 (%)":
                val = (df_loc['IsStrike'].sum() / n_loc) * 100
                unit_str = "%"
            elif metric_choice == "インプレー時危険度 (被安打率 %)":
                n_inplay = df_loc['IsInPlay'].sum()
                val = (df_loc['IsHit'].sum() / n_inplay * 100) if n_inplay > 0 else 0.0
                unit_str = "%"
            else:  # 高度危険度スコア (平均)
                val = df_loc['DangerScore'].mean()
                unit_str = " pt"
                
            grid_matrix[r, c] = round(val, 2)
            text_matrix[r, c] = f"<b>{zone_names[loc]}</b><br><b>{val:.2f}{unit_str}</b><br>({n_loc}球)"
        else:
            text_matrix[r, c] = f"<b>{zone_names[loc]}</b><br>データ無"

    # -------------------------------------------------------------------------
    # ヒートマップ描画 (Plotly)
    # -------------------------------------------------------------------------
    colorscale = "Blues" if metric_choice == "ストライク奪取率 (%)" else "Reds"

    fig_hm = px.imshow(
        grid_matrix,
        x=x_axis_labels,
        y=['高め', 'ベルトライン', '低め'],
        text_auto=False,
        color_continuous_scale=colorscale,
        aspect="auto"
    )
    
    fig_hm.update_traces(
        text=text_matrix,
        texttemplate="%{text}",
        hovertemplate="コース: %{x}-%{y}<br>値: %{z}<extra></extra>"
    )
    
    fig_hm.update_layout(
        title=f"コース別 {metric_choice} （【対 {target_batter_lr}】 / 捕手目線）",
        height=480,
        margin=dict(l=20, r=20, t=50, b=30)
    )

    st.plotly_chart(fig_hm, use_container_width=True)
