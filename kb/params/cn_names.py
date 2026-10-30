# -*- coding: utf-8 -*-
"""canonical 参数中文映射表（报告/前端展示用；内核仍用 canonical 名——铁律2）。

凡注册表参数必须有中文条目；缺失时报告回退显示 canonical 名（不阻塞）。
"""
CN_NAMES = {
    # 站点/资源
    "site.latitude_deg": ("站点纬度", "站点与资源"),
    # 光伏
    "pv.capacity_kw": ("光伏装机容量", "光伏"),
    "pv.derate": ("光伏综合折减系数", "光伏"),
    "econ.pv_capex_per_kw": ("光伏单位投资", "光伏"),
    "econ.pv_life_years": ("光伏寿命", "光伏"),
    "econ.pv_opex_ratio": ("光伏年运维费率", "光伏"),
    # 风电
    "wind.capacity_kw": ("风电装机容量", "风电"),
    "wind.cut_in_ms": ("风机切入风速", "风电"),
    "wind.rated_ms": ("风机额定风速", "风电"),
    "wind.cut_out_ms": ("风机切出风速", "风电"),
    "econ.wind_capex_per_kw": ("风电单位投资", "风电"),
    "econ.wind_life_years": ("风电寿命", "风电"),
    "econ.wind_opex_ratio": ("风电年运维费率", "风电"),
    # 储能电池
    "bess.capacity_kwh": ("锂电池容量", "电储能"),
    "bess.power_kw": ("锂电池额定功率", "电储能"),
    "bess.eff_roundtrip": ("电池往返效率", "电储能"),
    "bess.soc_min": ("电池最低荷电状态", "电储能"),
    "bess.soc_max": ("电池最高荷电状态", "电储能"),
    "bess.soc_init": ("电池初始荷电状态", "电储能"),
    "econ.bess_capex_per_kwh": ("电池单位投资", "电储能"),
    "econ.bess_life_years": ("电池寿命", "电储能"),
    "econ.bess_opex_ratio": ("电池年运维费率", "电储能"),
    # 电解（PEM）
    "pemwe.rated_kw": ("PEM 电解槽额定功率", "电解制氢"),
    "pemwe.eff_lhv": ("PEM 电解效率(LHV)", "电解制氢"),
    "pemwe.min_load_ratio": ("PEM 最小负荷率", "电解制氢"),
    "econ.pemwe_capex_per_kw": ("PEM 单位投资", "电解制氢"),
    "econ.pemwe_life_years": ("PEM 电解槽寿命", "电解制氢"),
    # 燃料电池
    "fc.rated_kw": ("燃料电池额定功率", "燃料电池"),
    "fc.eff_lhv": ("燃料电池效率(LHV)", "燃料电池"),
    "econ.fc_capex_per_kw": ("燃料电池单位投资", "燃料电池"),
    "econ.fc_life_years": ("燃料电池寿命", "燃料电池"),
    "econ.fc_opex_ratio": ("燃料电池年运维费率", "燃料电池"),
    # 负荷
    "load.avg_kw": ("平均电负荷", "负荷"),
    "load.night_ratio": ("夜间负荷比", "负荷"),
    # 储氢
    "h2store.capacity_kg": ("储氢容量", "储氢"),
    "h2store.level_init_kg": ("储氢初始存量", "储氢"),
    "econ.h2store_capex_per_kg": ("储氢单位投资", "储氢"),
    "econ.h2store_life_years": ("储氢设施寿命", "储氢"),
    # 液氢储氢（LH2）
    "lh2.liquefaction_kwh_per_kg": ("液氢单位液化电耗", "液氢"),
    "lh2.boil_off_ratio_per_day": ("液氢日蒸发率", "液氢"),
    # 压缩机
    "comp.eta_iso": ("压缩机等温效率", "压缩机"),
    "comp.p_in_bar": ("压缩机入口压力", "压缩机"),
    "comp.p_out_bar": ("压缩机出口压力", "压缩机"),
    # 固态储氢（PMHT）
    "mh.bed_mass_kg": ("固态储氢床质量", "固态储氢"),
    "mh.uth_w_per_k": ("床-环境传热系数", "固态储氢"),
    "mh.p_supply_pa": ("电解供氢压力", "固态储氢"),
    "mh.p_bus_pa": ("氢母线压力", "固态储氢"),
    "mh.t_ambient_k": ("环境/冷却介质温度", "固态储氢"),
    # 电网
    "grid.max_import_kw": ("购电容量红线", "电网"),
    "grid.ppa_price_cny_kwh": ("绿电直连合同电价", "电网"),
    "grid.buy_peak_cny_kwh": ("分时购电·峰段电价", "电网"),
    "grid.buy_flat_cny_kwh": ("分时购电·平段电价", "电网"),
    "grid.buy_valley_cny_kwh": ("分时购电·谷段电价", "电网"),
    "grid.sell_price_cny_kwh": ("上网售电电价", "电网"),
    # 化工/冶金
    "chem.nh3.capacity_t_per_h": ("合成氨装置额定产量", "合成氨"),
    "chem.nh3.h2_per_t_kg": ("吨氨耗氢", "合成氨"),
    "chem.nh3.lec_mwh_per_t": ("吨氨合成电耗", "合成氨"),
    "chem.nh3.min_load": ("合成氨最小稳定负荷", "合成氨"),
    "chem.nh3.ramp_per_h": ("合成氨每小时爬坡率", "合成氨"),
    "chem.asu.lec_kwh_per_kg_n2": ("空分制氮电耗", "空分"),
    "chem.meoh.h2_per_t_kg": ("吨醇耗氢", "甲醇"),
    "chem.meoh.co2_per_t_kg": ("吨醇耗CO2", "甲醇"),
    "chem.meoh.min_load": ("甲醇最小稳定负荷", "甲醇"),
    "chem.dri.h2_per_t_fe_kg": ("吨铁耗氢", "氢冶金"),
    "chem.dri.min_load": ("直接还原炉最小负荷", "氢冶金"),
    # 多电解路线
    "alk.rated_kw": ("碱性电解槽额定功率", "电解制氢"),
    "alk.eff_lhv": ("碱性电解效率(LHV)", "电解制氢"),
    "alk.min_load_ratio": ("碱性电解最小负荷率", "电解制氢"),
    "aem.rated_kw": ("AEM 电解槽额定功率", "电解制氢"),
    "aem.eff_lhv": ("AEM 电解效率(LHV)", "电解制氢"),
    "aem.min_load_ratio": ("AEM 最小负荷率", "电解制氢"),
    "soec.rated_kw": ("SOEC 高温电解额定功率", "电解制氢"),
    "soec.eff_lhv": ("SOEC 热中性效率(LHV)", "电解制氢"),
    "soec.eff_lhv_no_heat": ("SOEC 缺热降额效率", "电解制氢"),
    "soec.min_load_ratio": ("SOEC 最小负荷率", "电解制氢"),
    "soec.heat_available": ("SOEC 余热可用(0/1)", "电解制氢"),
    "sofc.rated_kw": ("SOFC 额定功率", "燃料电池"),
    "sofc.eff_lhv": ("SOFC 发电效率(LHV)", "燃料电池"),
    "sofc.min_load_ratio": ("SOFC 最小负荷率", "燃料电池"),
    "sofc.heat_to_power_ratio": ("SOFC 余热/发电比", "燃料电池"),
    # 优化
    "opt.reliability_target": ("保供率硬约束", "优化"),
    "opt.top_n": ("优化输出配置数", "优化"),
    "opt.max_combinations": ("穷举组合数上限", "优化"),
    # 经济
    "econ.project_years": ("项目周期", "经济性"),
    "econ.discount_rate": ("贴现率", "经济性"),
    "econ.wind_capex_per_kw": ("风电单位投资", "经济性"),
    "econ.wind_life_years": ("风电寿命", "经济性"),
    "econ.wind_opex_ratio": ("风电年运维费率", "经济性"),
    "econ.nh3_capex_cny_per_t_per_h": ("合成氨装置单位投资", "经济性"),
    "econ.nh3_life_years": ("合成氨装置寿命", "经济性"),
    "econ.nh3_opex_ratio": ("合成氨装置年运维费率", "经济性"),
    "econ.alk_capex_per_kw": ("碱性电解单位投资", "经济性"),
    "econ.aem_capex_per_kw": ("AEM 单位投资", "经济性"),
    "econ.soec_capex_per_kw": ("SOEC 单位投资", "经济性"),
    "econ.alk_life_years": ("碱性电解寿命", "经济性"),
    "econ.aem_life_years": ("AEM 寿命", "经济性"),
    "econ.soec_life_years": ("SOEC 寿命", "经济性"),
    "econ.co2_price_cny_per_t": ("CO2 配额价格", "经济性"),
    "econ.grey_h2_co2_t_per_t": ("绿氢替灰氢吨氢减碳量", "经济性"),
    "econ.nh3_price_cny_per_t": ("液氨售价", "经济性"),
    "econ.meoh_price_cny_per_t": ("甲醇售价", "经济性"),
    "econ.dri_price_cny_per_t": ("直接还原铁售价", "经济性"),
    "econ.co2_capture_cost_cny_per_t": ("CO2 捕集成本", "经济性"),
}


def cn_name(canonical: str) -> str:
    """canonical → 中文名（未注册的回退原名）。"""
    return CN_NAMES.get(canonical, (canonical, ""))[0]


def cn_category(canonical: str) -> str:
    return CN_NAMES.get(canonical, ("", ""))[1]
