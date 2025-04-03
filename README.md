# SYMPHONY: SYstematic Multi-Product Hydrogen Optimization Network Yondervision

## Introduction
SYMPHONY (SYstematic Multi-Product Hydrogen Optimization Network Yondervision) is a global 0.25-degree grid-level optimization model aimed at optimizing the integrated production of hydrogen, ammonia, methanol, and other products synthesized using CO2 hydrogenation. This model comprehensively integrates various components including electricity generation (wind power, photovoltaics (PV)), energy storage, hydrogen production, heat management, Direct Air Capture - DAC, as well as the production and storage of terminal products such as hydrogen, ammonia, and methanol.

## Features
- Multi-product synthesis optimization (Hydrogen, Ammonia, Methanol, and potentially other CO2-derived products). (CG: this sounds like all production are optimized together (i.e. production plant of ammonia is optimized together with Methanol plant, i.e. when methanol tank is full, ammonia plant can be prioritized - is this the case? It looks like now it is one script per liquid)
- Integration of renewable energy sources: Wind power, PV, energy storage systems.
- Integration of heat production, hydyrogen production, liquid molecule synthesis and carbon supply. 
- Support for various time aggregation scales: hourly, 3-hourly, daily, weekly, monthly, and annual.
- Utilization of the Gurobi optimizer for efficient computation.

## Requirements
- Python 3.8+
- Gurobi
- pandas
- matplotlib
- numpy

## Installation
Install the required packages via pip:
```
pip install pandas matplotlib numpy gurobipy
```

## File Structure
- `Hydrogen.py`: Optimization model for hydrogen production using renewable energy and DAC.
- `Ammonia.py`: Optimization model for ammonia production based on hydrogen.
- `Methanol.py`: Optimization model for methanol production using hydrogen and CO2.
- `CF_NM_2023.csv`: Input data file containing renewable energy capacity factors time series for wind and PV for a given year.

## Usage
1. Ensure you have all the required dependencies installed.
(C: maybe here some instruction on obtaining Gurobi Academic license? https://www.gurobi.com/academia/academic-program-and-licenses/, btw did you get this license "Named-User Academic"?)
2. Place the `CF_NM_2023.csv` file in the same directory as the Python scripts.
3. Run the individual Python scripts for different production models:
```
python Hydrogen.py
python Ammonia.py
python Methanol.py
```

## Outputs
The model provides several outputs:
- Optimal system configuration (capacity of wind, PV, storage, and DAC systems).
- Cost breakdown and Levelized Cost of Electricity (LCOE), LCOH (of Hydrogen), LCOL (of Liquid)
- Various plots illustrating power balance, storage dynamics, and production profiles.
- Stacked bar charts for supply and demand visualization.

## Contact
Author: Qianzhi Zhang  
Affiliation: Tsinghua University, visiting scholar at The Potsdam Institute for Climate Impact Research (PIK)  
Email: zgz21@mails.tsinghua.edu.cn

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

