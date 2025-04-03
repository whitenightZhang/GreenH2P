# =============================================================================
# 3. 可再生能源制氢
# 3. Renewable hydrogen production
# =============================================================================

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import gurobipy as gp
from gurobipy import Model, GRB

# =============================================================================
# 1. 数据加载
# 1. data loading
# =============================================================================
# 请确保文件 "CF_NM_2023.csv" 存在且第一列为PV数据、第二列为风电数据
# Please make sure file "CF_NM_2023.csv" exists, and the first column is PV data, the second column is win data
wind_solar_data = pd.read_csv('CF_NM_2023.csv')
pv_output   = wind_solar_data.iloc[:, 0].values   # 光伏输出曲线（无量纲或功率比例）(PV theoretical capacity factor)
wind_output = wind_solar_data.iloc[:, 1].values   # 风电输出曲线 (Wind theoretical capacity factor)

# =============================================================================
# 2. 参数定义
# 2. Parameter definitions
# =============================================================================
# 2.1 可再生能源与电池参数
# 2.1 renewable and battery parameters
wind_cost = 800            # 风电安装成本 ($/kW) # wind installation cost ($/kW)
pv_cost   = 300            # 光伏安装成本 ($/kW) # PV installation cost ($/kW)
battery_cost = 150         # 储能安装成本 ($/kW) # battery installation cost ($/kW)
battery_efficiency = 0.98  # LFP's efficiency is around 92-94% NCA 91-93% https://www.sandia.gov/ess-ssl/docs/pr_conferences/2016/Monday_Presentations/27_Daiwon_Choi.pdf
# C: There is no E_2_P ratio?
# There should be 2 investment costs? One for E (energy), one for P (power)?
# e.g. in DIETER: stodata("c_inv_overnight_sto_e",sto) = stodata("c_inv_overnight_sto_p",sto) / stodata("e_to_p",sto);
battery_charge_penalty = 0.00001  # ($/kWh)
battery_discharge_penalty = 0.000 # ($/kWh)
battery_om = battery_cost * 0.03
battery_lifetime = 15
wind_lifetime = 20
pv_lifetime = 25

# 2.2 电解槽参数（制氢设备，分AE与PEM两种）
# 2.2. Electrolyzer parameters (hydrogen productin equipment, AE (Alkaline) and PEM (Proton Exchange Membrane) two types
electrolyzer_cost_AE = 300      # ($/kW)
electrolyzer_cost_PEM = 500      # ($/kW)
electrolyzer_om_AE = electrolyzer_cost_AE * 0.03
electrolyzer_om_PEM = electrolyzer_cost_PEM * 0.03
electrolyzer_lifetime = 15
electrolyzer_eff = 0.7       # Electrolyzer efficiency

# 2.3 氢气存储参数
# 2.3 hydrogen storage parameters (above ground, with compression?)
hydrogen_storage_cost = 1500  # ($/kg)
hydrogen_storage_om   = hydrogen_storage_cost * 0.03
hydrogen_charge_penalty = 0.00001  # ($/kgH2)
hydrogen_storage_efficiency = 0.9 (referene https://www.sciencedirect.com/science/article/abs/pii/S2352152X22005114 ? )
hydrogen_storage_elec = 0.33       # kWh/kg H2（充氢所需电耗）
hydrogen_storage_lifetime = 25     

# 2.4 目标制氢参数
# 2.4 Hydrogen demand
target_hydrogen_production = 10 * 1000  # kg/年，即10吨/年
hourly_hydrogen_demand = target_hydrogen_production / 8760

# 2.5 年化成本计算（折现率）
# 2.5 Annualtization of costs
discount_rate = 0.07
wind_annual_cost = wind_cost * discount_rate / (1 - (1 + discount_rate) ** -wind_lifetime) + wind_cost * 0.03
pv_annual_cost = pv_cost * discount_rate / (1 - (1 + discount_rate) ** -pv_lifetime) + pv_cost * 0.03
battery_annual_cost = battery_cost * discount_rate / (1 - (1 + discount_rate) ** -battery_lifetime) + battery_om
electrolyzer_annual_cost_AE = electrolyzer_cost_AE * discount_rate / (1 - (1 + discount_rate) ** -electrolyzer_lifetime) + electrolyzer_om_AE
electrolyzer_annual_cost_PEM = electrolyzer_cost_PEM * discount_rate / (1 - (1 + discount_rate) ** -electrolyzer_lifetime) + electrolyzer_om_PEM
hydrogen_storage_annual_cost = hydrogen_storage_cost * discount_rate / (1 - (1 + discount_rate) ** -hydrogen_storage_lifetime) + hydrogen_storage_om

# 2.6 逐时灵活性参数（限制电解槽功率变化率）(C: a bit more explanation here)
# 2.6 Hourly flexibility parameters (restrict rate of change of electrolyzer power)
Flex_up = 0.05  
Flex_mid = 0.1  
Flex_down = 0.2  
surplus_penalty = 0.00001

# 2.7 供需平衡聚合尺度选择
# 2.7 Supply-demand balance aggregation dimension
# 可选值："hourly"、"3hourly"、"daily"、"weekly"、"monthly"、"annual"
# Can choose from: "hourly"、"3hourly"、"daily"、"weekly"、"monthly"、"annual"
aggregation_mode = "annual"

# =============================================================================
# 3. 模型创建与变量定义
# 3. Model build and variable definition
# =============================================================================
model = Model("HydrogenProductionOptimization")
# 设置模型求解参数
# Set solver parameters
model.setParam('TimeLimit', 1000)
model.setParam('MIPFocus', 1)
model.setParam('Threads', 1)
model.setParam('MIPGap', 0.1) 
model.setParam('Method', 2)
model.setParam('Crossover', 0)

time_steps = 8760

# 3.1 装机设备决策变量
wind_capacity = model.addVar(lb=0, name="wind_capacity")
pv_capacity   = model.addVar(lb=0, name="pv_capacity")
battery_capacity = model.addVar(lb=0, name="battery_capacity")
hydrogen_storage_capacity = model.addVar(lb=0, name="hydrogen_storage_capacity")

# 分别定义 AE 与 PEM 型电解槽装机决策变量
electrolyzer_capacity_AE = model.addVar(lb=0, name="electrolyzer_capacity_AE")
electrolyzer_capacity_PEM = model.addVar(lb=0, name="electrolyzer_capacity_PEM")

# 3.2 时间步相关变量（共8760小时）
# 电解槽出力变量
electrolyzer_power_AE = model.addVars(time_steps, lb=0, name="electrolyzer_power_AE")
electrolyzer_power_PEM = model.addVars(time_steps, lb=0, name="electrolyzer_power_PEM")

# 电池储能相关变量
energy_balance = model.addVars(time_steps, lb=0, name="energy_balance") #"electricity balance" may be better?
battery_charge = model.addVars(time_steps, lb=0, name="battery_charge")
battery_discharge = model.addVars(time_steps, lb=0, name="battery_discharge")

# 多余电量变量（未利用电量）
surplus = model.addVars(time_steps, lb=0, name="surplus")

# 氢气存储相关变量
# https://www.sciencedirect.com/science/article/pii/S036031992404028X
hydrogen_storage_balance = model.addVars(time_steps, lb=0, name="hydrogen_storage_balance")
hydrogen_charge = model.addVars(time_steps, lb=0, name="hydrogen_charge")
hydrogen_discharge = model.addVars(time_steps, lb=0, name="hydrogen_discharge")

# =============================================================================
# 4. 目标函数
# =============================================================================
model.setObjective(
    wind_annual_cost * wind_capacity +
    pv_annual_cost * pv_capacity +
    battery_annual_cost * battery_capacity +
    electrolyzer_annual_cost_AE * electrolyzer_capacity_AE + 
    electrolyzer_annual_cost_PEM * electrolyzer_capacity_PEM +
    hydrogen_storage_annual_cost * hydrogen_storage_capacity +
    surplus_penalty * gp.quicksum(surplus[t] for t in range(time_steps)) +
    battery_charge_penalty * gp.quicksum(battery_charge[t] for t in range(time_steps)) +
    battery_discharge_penalty * gp.quicksum(battery_discharge[t] for t in range(time_steps)) +
    hydrogen_charge_penalty * gp.quicksum(hydrogen_charge[t] for t in range(time_steps)),
    GRB.MINIMIZE
)

# =============================================================================
# 5. 约束条件
# =============================================================================

# 5.1 逐时设备灵活性约束（仅针对 AE 型电解槽，限制功率变化）
for t in range(1, time_steps):
    model.addConstr(electrolyzer_power_AE[t] - electrolyzer_power_AE[t-1] <= Flex_mid * electrolyzer_capacity_AE,
                    name=f"electrolyzer_AE_ramp_up_{t}")
    model.addConstr(electrolyzer_power_AE[t] - electrolyzer_power_AE[t-1] >= -Flex_mid * electrolyzer_capacity_AE,
                    name=f"electrolyzer_AE_ramp_down_{t}")

# 5.2 电力平衡约束（逐时）
for t in range(time_steps):
    wind_power = wind_output[t] * wind_capacity
    pv_power = pv_output[t] * pv_capacity
    model.addConstr(
        wind_power + pv_power + battery_discharge[t] ==
        (electrolyzer_power_AE[t] + electrolyzer_power_PEM[t]) +
        battery_charge[t] + hydrogen_charge[t] * hydrogen_storage_elec + surplus[t],
        name=f"power_balance_{t}"
    )
    # 电池储能与充放电限制
    model.addConstr(energy_balance[t] <= battery_capacity,
                    name=f"energy_balance_limit_{t}")
    model.addConstr(battery_charge[t] + battery_discharge[t] <= battery_capacity,
                    name=f"battery_charge_discharge_limit_{t}")
    # 电池动态平衡
    if t == 0:
        model.addConstr(
            energy_balance[t] == battery_charge[t] * battery_efficiency - battery_discharge[t] / battery_efficiency,
            name=f"battery_balance_{t}"
        )
    else:
        model.addConstr(
            energy_balance[t] == energy_balance[t-1] + battery_charge[t] * battery_efficiency - battery_discharge[t] / battery_efficiency,
            name=f"battery_balance_{t}"
        )

# 5.3 氢气供需平衡约束（支持不同时间聚合尺度）
# 转换系数：电解槽产氢量 = 出力 * electrolyzer_eff * 3.6/120 (C: 3.6/120?)
conversion_factor = electrolyzer_eff * 3.6 / 120

if aggregation_mode == "hourly":
    for t in range(168, time_steps):
        model.addConstr(
            (electrolyzer_power_AE[t] + electrolyzer_power_PEM[t]) * conversion_factor + hydrogen_discharge[t] >=
            0.8 * hourly_hydrogen_demand + hydrogen_charge[t],
            name=f"hydrogen_balance_{t}"
        )
elif aggregation_mode == "3hourly":
    interval = 3
    start_index = 168
    n_intervals = (time_steps - start_index) // interval
    for i in range(n_intervals):
        t_start = start_index + i * interval
        t_end = t_start + interval
        model.addConstr(
            gp.quicksum((electrolyzer_power_AE[t] + electrolyzer_power_PEM[t]) * conversion_factor for t in range(t_start, t_end)) +
            gp.quicksum(hydrogen_discharge[t] for t in range(t_start, t_end))
            >= hourly_hydrogen_demand * interval +
            gp.quicksum(hydrogen_charge[t] for t in range(t_start, t_end)),
            name=f"hydrogen_balance_3hourly_{i}"
        )
elif aggregation_mode == "daily":
    interval = 24
    start_index = 168
    n_intervals = (time_steps - start_index) // interval
    for i in range(n_intervals):
        t_start = start_index + i * interval
        t_end = t_start + interval
        model.addConstr(
            gp.quicksum((electrolyzer_power_AE[t] + electrolyzer_power_PEM[t]) * conversion_factor for t in range(t_start, t_end)) +
            gp.quicksum(hydrogen_discharge[t] for t in range(t_start, t_end))
            >= 0.8 * hourly_hydrogen_demand * interval +
            gp.quicksum(hydrogen_charge[t] for t in range(t_start, t_end)),
            name=f"hydrogen_balance_daily_{i}"
        )
elif aggregation_mode == "weekly":
    interval = 168  # 1周 = 168小时
    start_index = 168
    n_intervals = (time_steps - start_index) // interval
    for i in range(n_intervals):
        t_start = start_index + i * interval
        t_end = t_start + interval
        model.addConstr(
            gp.quicksum((electrolyzer_power_AE[t] + electrolyzer_power_PEM[t]) * conversion_factor for t in range(t_start, t_end)) +
            gp.quicksum(hydrogen_discharge[t] for t in range(t_start, t_end))
            >= hourly_hydrogen_demand * interval +
            gp.quicksum(hydrogen_charge[t] for t in range(t_start, t_end)),
            name=f"hydrogen_balance_weekly_{i}"
        )
elif aggregation_mode == "monthly":
    interval = 730
    start_index = 168
    n_intervals = (time_steps - start_index) // interval
    for i in range(n_intervals):
        t_start = start_index + i * interval
        t_end = t_start + interval
        model.addConstr(
            gp.quicksum((electrolyzer_power_AE[t] + electrolyzer_power_PEM[t]) * conversion_factor for t in range(t_start, t_end)) +
            gp.quicksum(hydrogen_discharge[t] for t in range(t_start, t_end))
            >= hourly_hydrogen_demand * interval +
            gp.quicksum(hydrogen_charge[t] for t in range(t_start, t_end)),
            name=f"hydrogen_balance_monthly_{i}"
        )
elif aggregation_mode == "annual":
    model.addConstr(
        gp.quicksum((electrolyzer_power_AE[t] + electrolyzer_power_PEM[t]) * conversion_factor for t in range(168, time_steps)) +
        gp.quicksum(hydrogen_discharge[t] for t in range(168, time_steps))
        >= hourly_hydrogen_demand * (time_steps - 168) +
        gp.quicksum(hydrogen_charge[t] for t in range(168, time_steps)),
        name="hydrogen_balance_annual"
    )
else:
    raise ValueError("Unsupported aggregation_mode value!")

# 附加：年生产总量约束
model.addConstr(
    gp.quicksum((electrolyzer_power_AE[t] + electrolyzer_power_PEM[t]) * conversion_factor for t in range(time_steps)) >= hourly_hydrogen_demand * 8760,
    name="annual_hydrogen_production_constraint"
)

# 5.4 氢气储存动态平衡及容量限制
model.addConstr(hydrogen_storage_balance[0] == hydrogen_charge[0] - hydrogen_discharge[0],
                name="hydrogen_storage_balance_0")
for t in range(1, time_steps):
    model.addConstr(
        hydrogen_storage_balance[t] == hydrogen_storage_balance[t-1] + hydrogen_charge[t] - hydrogen_discharge[t],
        name=f"hydrogen_storage_balance_{t}"
    )
    model.addConstr(hydrogen_storage_balance[t] <= hydrogen_storage_capacity,
                    name=f"hydrogen_storage_level_limit_{t}")
    model.addConstr(hydrogen_charge[t] + hydrogen_discharge[t] <= hydrogen_storage_capacity,
                    name=f"hydrogen_charge_limit_{t}")

# 5.5 装机容量约束
model.addConstrs((electrolyzer_capacity_AE >= electrolyzer_power_AE[t] for t in range(time_steps)),
                 name="electrolyzer_AE_capacity_constraint")
model.addConstrs((electrolyzer_capacity_PEM >= electrolyzer_power_PEM[t] for t in range(time_steps)),
                 name="electrolyzer_PEM_capacity_constraint")
model.addConstrs((electrolyzer_power_AE[t] >= 0.1 * electrolyzer_capacity_AE for t in range(168, time_steps)),
                 name="electrolyzer_AE_power_constraint")

# 5.6 附加：要求AE型电解槽必须配备至少0.5倍（约10%）的储能电池
model.addConstr(battery_capacity >= 0.5 * electrolyzer_capacity_AE,
                name="min_battery_for_AE")

# =============================================================================
# 6. 求解模型
# =============================================================================
model.optimize()

# =============================================================================
# 7. 输出结果
# =============================================================================
if model.status == GRB.OPTIMAL:
    total_hydrogen_production = sum((electrolyzer_power_AE[t].x + electrolyzer_power_PEM[t].x) * conversion_factor for t in range(time_steps))
    hydrogen_production_kwh = sum((electrolyzer_power_AE[t].x + electrolyzer_power_PEM[t].x) for t in range(time_steps)) * electrolyzer_eff
    electrolyzer_utilization_hours = hydrogen_production_kwh / ((electrolyzer_capacity_AE.x + electrolyzer_capacity_PEM.x) * electrolyzer_eff * 8760) * 100
    hydrogen_storage_kwh = sum(hydrogen_charge[t].x * hydrogen_storage_elec for t in range(time_steps))
    total_Elec_generation = (sum(wind_output[t] for t in range(time_steps)) * wind_capacity.x +
                             sum(pv_output[t] for t in range(time_steps)) * pv_capacity.x -
                             sum(surplus[t].x for t in range(time_steps)))
    
    levelized_Elec_cost = (
        wind_annual_cost * wind_capacity.x +
        pv_annual_cost * pv_capacity.x +
        battery_annual_cost * battery_capacity.x +
        battery_charge_penalty * sum(battery_charge[t].x for t in range(time_steps)) +
        battery_discharge_penalty * sum(battery_discharge[t].x for t in range(time_steps))
    ) / total_Elec_generation

    levelized_H2_cost = (
        electrolyzer_annual_cost_AE * electrolyzer_capacity_AE.x +
        electrolyzer_annual_cost_PEM * electrolyzer_capacity_PEM.x +
        levelized_Elec_cost * hydrogen_production_kwh / electrolyzer_eff +
        levelized_Elec_cost * hydrogen_storage_kwh +
        hydrogen_storage_annual_cost * hydrogen_storage_capacity.x
    ) / (hydrogen_production_kwh / 33.3)

    print("Optimal system configuration:")
    print(f"Wind capacity: {wind_capacity.x:.2f} kW")
    print(f"PV capacity: {pv_capacity.x:.2f} kW")
    print(f"Battery capacity: {battery_capacity.x:.2f} kW")
    print(f"AE Electrolyzer capacity: {electrolyzer_capacity_AE.x:.2f} kW")
    print(f"PEM Electrolyzer capacity: {electrolyzer_capacity_PEM.x:.2f} kW")
    print(f"Total hydrogen production: {total_hydrogen_production:.2f} kg")
    print(f"Electrolyzer utilization hours: {electrolyzer_utilization_hours:.2f} %")
    print(f"Levelized Elec cost: ${levelized_Elec_cost:.2f} per kWh")
    print(f"Levelized H2 cost: ${levelized_H2_cost:.2f} per kgH2")
    print(f"Levelized hydrogen production cost: ${model.objVal / total_hydrogen_production:.2f} per kg")
else:
    print("No feasible solution found.")

# =============================================================================
# 8. 折线图
# =============================================================================
if model.status == GRB.OPTIMAL:
    print("Optimal system configuration:")
    print(f"Wind capacity: {wind_capacity.x:.2f} kW")
    print(f"PV capacity: {pv_capacity.x:.2f} kW")
    print(f"Battery capacity: {battery_capacity.x:.2f} kW")
    print(f"Electrolyzer capacity_AE: {electrolyzer_capacity_AE.x:.2f} kW")
    print(f"Electrolyzer capacity_PEM: {electrolyzer_capacity_PEM.x:.2f} kW")
    print(f"Hydrogen storage capacity: {hydrogen_storage_capacity.x:.2f} kgH2/h")
    print(f"Total hydrogen production: {total_hydrogen_production:.2f} kg")
    print(f"Electrolyzer utilization hours: {electrolyzer_utilization_hours:.2f} %")
    print(f"Levelized Elec cost: ${levelized_Elec_cost:.2f} per kWh")
    print(f"Levelized H2 cost: ${levelized_H2_cost:.2f} per kgH2")
    print(f"Levelized hydrogen production cost: ${model.objVal / total_hydrogen_production:.2f} per kg")

    # 计算各时刻功率和储能曲线
    wind_power_profile = wind_output * wind_capacity.x
    pv_power_profile = pv_output * pv_capacity.x
    electrolyzer_demand_AE = [electrolyzer_power_AE[t].x * electrolyzer_eff for t in range(time_steps)]
    electrolyzer_demand_PEM = [electrolyzer_power_PEM[t].x * electrolyzer_eff for t in range(time_steps)]
    hydrogen_storage_profile = [hydrogen_storage_balance[t].x for t in range(time_steps)]
    
    # 获取各时刻电力平衡约束和氢气小时供需平衡约束的对偶价格
    electricity_prices = [model.getConstrByName(f"power_balance_{t}").pi for t in range(time_steps)]
    hydrogen_prices = []
    for t in range(time_steps):
        constr = model.getConstrByName(f"hydrogen_balance_{t}")
        if constr is not None:
            hydrogen_prices.append(constr.pi)
        else:
            hydrogen_prices.append(0)

    # 绘制一个样本周（168小时）的时序图
    week_start = 168 * 10   # 例如，从第11周开始
    week_end = week_start + 168

    battery_charge_profile_week = [battery_charge[t].x for t in range(week_start, week_end)]
    battery_discharge_profile_week = [battery_discharge[t].x for t in range(week_start, week_end)]
    energy_balance_profile_week = [energy_balance[t].x for t in range(week_start, week_end)]
    wind_power_profile_week = wind_power_profile[week_start:week_end]
    pv_power_profile_week = pv_power_profile[week_start:week_end]
    electrolyzer_demand_week_AE = [electrolyzer_demand_AE[t] for t in range(week_start, week_end)]
    electrolyzer_demand_week_PEM = [electrolyzer_demand_PEM[t] for t in range(week_start, week_end)]
    hydrogen_storage_week = [hydrogen_storage_profile[t] for t in range(week_start, week_end)]
    
    electricity_prices_week = electricity_prices[week_start:week_end]
    hydrogen_prices_week = hydrogen_prices[week_start:week_end]

    plt.figure(figsize=(15, 8))
    plt.plot(wind_power_profile_week, label='Wind Output (kW)', linestyle='-', color='blue')
    plt.plot(pv_power_profile_week, label='PV Output (kW)', linestyle='-', color='orange')
    plt.plot(battery_charge_profile_week, label='Battery Charge (kW)', linestyle='--', color='green')
    plt.plot(battery_discharge_profile_week, label='Battery Discharge (kW)', linestyle='--', color='red')
    plt.plot(electrolyzer_demand_week_AE, label='Electrolyzer Demand AE(kW)', linestyle='-', color='purple')
    plt.plot(electrolyzer_demand_week_PEM, label='Electrolyzer Demand PEM(kW)', linestyle='-', color='red')
    plt.plot(hydrogen_storage_week, label='Hydrogen Storage Balance (kg)', linestyle='-', color='cyan')
    plt.plot(electricity_prices_week, label='Electricity Price ($/kWh)', linestyle='-', color='blue')
    plt.plot(hydrogen_prices_week, label='Hydrogen Price ($/kg)', linestyle='-', color='green')

    plt.xlabel('Hour')
    plt.ylabel('Value')
    plt.title('Power Output and Demand Profiles (Sample Week)')
    plt.legend()
    plt.grid(True)
    plt.show()

    # 按月绘图
    hours_in_month = [0, 744, 1416, 2160, 2880, 3624, 4344, 5088, 5832, 6552, 7296, 8016, 8760]
    month_names = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

    for i in range(12):
        start = hours_in_month[i]
        end = hours_in_month[i + 1]

        battery_charge_profile = [battery_charge[t].x for t in range(start, end)]
        battery_discharge_profile = [battery_discharge[t].x for t in range(start, end)]
        energy_balance_profile = [energy_balance[t].x for t in range(start, end)]

        plt.figure(figsize=(15, 8))
        plt.plot(wind_power_profile[start:end], label='Wind Output (kW)', linestyle='-', color='blue')
        plt.plot(pv_power_profile[start:end], label='PV Output (kW)', linestyle='-', color='orange')
        plt.plot(battery_charge_profile, label='Battery Charge (kW)', linestyle='--', color='green')
        plt.plot(battery_discharge_profile, label='Battery Discharge (kW)', linestyle='--', color='red')
        plt.plot(electrolyzer_demand_AE[start:end], label='Electrolyzer Demand AE (kW)', linestyle='-', color='purple')
        plt.plot(electrolyzer_demand_PEM[start:end], label='Electrolyzer Demand PEM (kW)', linestyle='-', color='purple')
        plt.plot(hydrogen_storage_profile[start:end], label='Hydrogen Storage Balance (kg)', linestyle='-', color='cyan')
        plt.plot(electricity_prices[start:end], label='Electricity Price ($/kWh)', linestyle='-', color='blue')
        plt.plot(hydrogen_prices[start:end], label='Hydrogen Price ($/kg)', linestyle='-', color='green')

        plt.xlabel('Hour')
        plt.ylabel('Value')
        plt.title(f'Power Output and Demand Profiles ({month_names[i]})')
        plt.legend()
        plt.grid(True)
        plt.show()
else:
    print("No feasible solution found.")

# =============================================================================
# 9. 堆积图-电力平衡
# =============================================================================
if model.status == GRB.OPTIMAL:
    # ---------------------------
    # 样本周（168小时）堆积柱状图
    # ---------------------------
    week_start = 168 * 10   # 例如取第11周
    week_end = week_start + 168
    x = np.arange(week_end - week_start)

    # 供给侧：风电、光伏、以及电池放电（均为正值）
    supply_wind = np.array([wind_output[t] * wind_capacity.x for t in range(week_start, week_end)])
    supply_pv = np.array([pv_output[t] * pv_capacity.x for t in range(week_start, week_end)])
    supply_battery = np.array([battery_discharge[t].x for t in range(week_start, week_end)])
    
    # 需求侧：电解槽、电池充电，以及氢气充电（乘以充氢所需电耗），显示为负值
    demand_electrolyzer_AE = np.array([electrolyzer_power_AE[t].x for t in range(week_start, week_end)])
    demand_electrolyzer_PEM = np.array([electrolyzer_power_PEM[t].x for t in range(week_start, week_end)])
    demand_battery = np.array([battery_charge[t].x for t in range(week_start, week_end)])
    demand_hydrogen = np.array([hydrogen_charge[t].x * hydrogen_storage_elec for t in range(week_start, week_end)])
    demand_surplus = np.array([surplus[t].x  for t in range(week_start, week_end)])
    
    plt.figure(figsize=(15, 8))
    # 绘制供给堆积柱状图（正值）
    bar1 = plt.bar(x, supply_wind, label='Wind Supply', color='blue')
    bar2 = plt.bar(x, supply_pv, bottom=supply_wind, label='PV Supply', color='orange')
    bar3 = plt.bar(x, supply_battery, bottom=supply_wind + supply_pv, label='Battery Discharge Supply', color='cyan')
    
    # 绘制需求堆积柱状图（负值）
    bar4 = plt.bar(x, -demand_electrolyzer_AE, label='Electrolyzer Demand AE', color='purple')
    bar5 = plt.bar(x, -demand_electrolyzer_PEM, bottom=-demand_electrolyzer_AE, label='Electrolyzer Demand PEM', color='yellow')
    bar6 = plt.bar(x, -demand_battery, bottom=-(demand_electrolyzer_AE+demand_electrolyzer_PEM), label='Battery Charge Demand', color='red')
    bar7 = plt.bar(x, -demand_hydrogen, bottom=-(demand_electrolyzer_AE+demand_electrolyzer_PEM + demand_battery), label='Hydrogen Charge Demand', color='green')
    bar8 = plt.bar(x, -demand_surplus, bottom=-(demand_electrolyzer_AE+demand_electrolyzer_PEM + demand_battery + demand_hydrogen), label='Surplus', color='brown')

    plt.axhline(0, color='black', linewidth=0.8)
    plt.xlabel('Hour')
    plt.ylabel('Power (kW)')
    plt.title('Stacked Power Supply (Positive) & Demand (Negative) - Sample Week')
    plt.legend(loc='upper right')
    plt.grid(True)
    plt.show()

    # ---------------------------
    # 按月堆积柱状图
    # ---------------------------
    # 近似每月小时数划分（可根据实际情况调整）
    hours_in_month = [0, 744, 1416, 2160, 2880, 3624, 4344, 5088, 5832, 6552, 7296, 8016, 8760]
    month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                   'July', 'August', 'September', 'October', 'November', 'December']

    for i in range(1):
        start = hours_in_month[i]
        end = hours_in_month[i + 1]
        x_month = np.arange(end - start)
        
        # 供给侧数据
        supply_wind_month = np.array([wind_output[t] * wind_capacity.x for t in range(start, end)])
        supply_pv_month = np.array([pv_output[t] * pv_capacity.x for t in range(start, end)])
        supply_battery_month = np.array([battery_discharge[t].x for t in range(start, end)])
        
        # 需求侧数据
        demand_electrolyzer_month_AE = np.array([electrolyzer_power_AE[t].x for t in range(start, end)])
        demand_electrolyzer_month_PEM = np.array([electrolyzer_power_PEM[t].x for t in range(start, end)])
        demand_battery_month = np.array([battery_charge[t].x for t in range(start, end)])
        demand_hydrogen_month = np.array([hydrogen_charge[t].x * hydrogen_storage_elec for t in range(start, end)])
        demand_surplus_month = np.array([surplus[t].x  for t in range(start, end)])
        
        plt.figure(figsize=(15, 8))
        plt.bar(x_month, supply_wind_month, label='Wind Supply', color='blue')
        plt.bar(x_month, supply_pv_month, bottom=supply_wind_month, label='PV Supply', color='orange')
        plt.bar(x_month, supply_battery_month, bottom=supply_wind_month + supply_pv_month, label='Battery Discharge Supply', color='cyan')
        
        plt.bar(x_month, -demand_electrolyzer_month_AE, label='Electrolyzer Demand AE', color='purple')
        plt.bar(x_month, -demand_electrolyzer_month_PEM, bottom=-demand_electrolyzer_month_AE, label='Electrolyzer Demand PEM', color='yellow')
        plt.bar(x_month, -demand_battery_month, bottom=-(demand_electrolyzer_month_AE + demand_electrolyzer_month_PEM), label='Battery Charge Demand', color='red')
        plt.bar(x_month, -demand_hydrogen_month, bottom=-(demand_electrolyzer_month_AE + demand_electrolyzer_month_PEM + demand_battery_month), label='Hydrogen Charge Demand', color='green')
        plt.bar(x_month, -demand_surplus_month, bottom=-(demand_electrolyzer_month_AE + demand_electrolyzer_month_PEM + demand_battery_month + demand_hydrogen_month), label='Surplus', color='brown')
        
        plt.axhline(0, color='black', linewidth=0.8)
        plt.xlabel('Hour')
        plt.ylabel('Power (kW)')
        plt.title(f'Stacked Power Supply & Demand ({month_names[i]})')
        plt.legend(loc='upper right')
        plt.grid(True)
        plt.show()
else:
    print("No feasible solution found.")
