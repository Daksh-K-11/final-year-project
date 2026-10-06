# FINAL YEAR CAPSTONE PROJECT (PHASE I) — FIRST REVIEW PRESENTATION DECK & SCRIPT

**Project Title:** Deep Learning-Based Air Quality Prediction Using Environmental Sensor Data  
**Track:** Track A (Environmental Monitoring & Machine Intelligence)  
**Institution:** Rajalakshmi Engineering College (REC)  
**Review Dates:** 25/08/2026 & 26/08/2026  

---

## SLIDE 1: Title Slide
- **Title:** Deep Learning-Based Air Quality Prediction Using Environmental Sensor Data
- **Domain:** Environmental Monitoring, Deep Learning & IoT Sensor Networks
- **Team Members & Roll Numbers:** Final Year Capstone Team (Track A)
- **Faculty Guide:** [Faculty Guide Name, Department of CSE/ECE]
- **Key Focus:** Multi-Pollutant Time-Series Forecasting, Temporal Attention, and Failure Mode Resilience.

> **Presenter Script:**  
> "Respected panel members and our faculty guide, good morning. Today we present our First Review progress for our Final Year Capstone Project titled 'Deep Learning-Based Air Quality Prediction Using Environmental Sensor Data'. Our project tackles hyper-local micro-climate forecasting using campus IoT telemetry and attention-driven deep learning models with explicit fault-tolerance analysis."

---

## SLIDE 2: Refined Problem Statement
- **Context:** Rapid urbanization and localized vehicular/industrial emissions create dangerous micro-climate hotspots.
- **The Gap:** Government reference stations (CAAQMS) are spatially sparse (1 station per 25-50 km²) and expensive ($50k-$100k), failing to capture university campus dynamics.
- **The Technical Challenge:** Low-cost IoT sensor networks suffer from:
  1. High-frequency sensor noise and calibration drift.
  2. Missing telemetry bursts from WiFi drops and hardware power outages.
  3. Seasonal and meteorological inversion distribution shifts.
- **Problem Statement:** To develop an accurate, robust deep learning framework capable of continuous CPCB AQI sub-index calculation, 24-hour ahead forecasting, and automated resilience against real-world hardware failures.

---

## SLIDE 3: Need and Significance of the Proposed Project
- **Health Impact:** $PM_{2.5}$ particles ($\le 2.5\mu m$) penetrate alveoli into the bloodstream, triggering respiratory and cardiovascular illnesses.
- **Proactive vs Reactive Intervention:** Predicting AQI 24 hours in advance allows university administration to issue alerts, reschedule outdoor sports, and optimize ventilation and bus transit.
- **Academic & Engineering Contribution:** First comprehensive framework combining official CPCB breakpoint equations with BiLSTM-Attention and empirical failure mode stress testing.

---

## SLIDE 4: Project Objectives
1. **Develop Ingestion & AQI Pipeline:** Ingest 9 environmental parameters ($PM_{2.5}, PM_{10}, NO_2, SO_2, CO, O_3, \text{Temp}, \text{Humidity}, \text{Wind}$) and calculate CPCB sub-indices.
2. **Formulate Deep Learning Models:** Implement Vanilla LSTM, BiLSTM with Temporal Attention, and Time-Series Transformer in PyTorch.
3. **Benchmark Against Baselines:** Compare with tree ensemble baselines (Random Forest Regressor) on $MAE$, $RMSE$, $R^2$, and AQI category classification accuracy.
4. **Conduct Failure Mode Stress Analysis:** Quantify degradation under Gaussian noise ($\sigma \le 0.60$), missing packet loss ($0-50\%$), and cross-seasonal distribution shifts.
5. **Deploy Interactive Platform:** Deliver a web monitoring portal with live telemetry and what-if simulation.

---

## SLIDE 5: Literature Survey & Research Gaps
- **Zhang et al. (IEEE TNNLS 2022):** Standard LSTM for urban $PM_{2.5}$. *Limitation:* Suffered from recency bias over 24h lookbacks.
- **Liang et al. (Elsevier 2023):** CNN-LSTM for spatial grids. *Limitation:* Computationally prohibitive for edge nodes.
- **Zhou et al. (AAAI Informer 2021):** Self-attention for time-series. *Limitation:* Overfitting on local sensor streams.
- **Sharma et al. (Springer 2023):** ARIMA and Random Forest on CPCB data. *Limitation:* Failed on non-linear smog inversions.
- **Our Identified Gaps:** Existing literature lacks multi-pollutant aggregate AQI modeling, ignores missing packet bursts, and rarely conducts hardware failure stress tests.

---

## SLIDE 6: Existing System vs. Proposed System

| Feature | Existing Systems | Proposed System (Our Work) |
|---|---|---|
| **Monitoring Scale** | Regional (1 per 30 km²) | Hyper-Local Campus Network (Multi-Node) |
| **Forecasting Model** | Linear ARIMA / Static ML | BiLSTM with Attention & Transformers |
| **AQI Standard** | Delayed 24h historical averages | Real-Time CPCB Sub-Index Formulation |
| **Fault Tolerance** | None (crashes or invalid outputs) | Imputation + Noise-Resilient Soft Attention |
| **Stress Testing** | None | Systematic Noise, Dropouts & Seasonal Suite |

---

## SLIDE 7: System Architecture & Workflow
- **Data Layer:** IoT Node Telemetry (Sensirion SPS30, Alphasense electrochemical sensors).
- **Preprocessing Layer:** IQR Outlier Capping, Linear Interpolation Imputation, Cyclical Encodings ($\sin/\cos$ hour, month, day of week), StandardScaler.
- **Modeling Layer:** 2-Layer BiLSTM with Soft Temporal Attention + Transformer Encoder.
- **Loss Function:** Huber Loss ($\text{Smooth } L_1$) for outlier resilience.
- **Application Layer:** FastAPI REST backend + Modern Glassmorphism Web Dashboard.

---

## SLIDE 8: Mathematical Formulation
- **CPCB Sub-Index:** $I_p = \frac{I_{high} - I_{low}}{B_{high} - B_{low}} (C_p - B_{low}) + I_{low}$
- **BiLSTM States:** $h_t = [\vec{h}_t \,\|\, \overleftarrow{h}_t] \in \mathbb{R}^{2d}$
- **Temporal Attention:** $e_t = v_a^T \tanh(W_a h_t + b_a), \quad \alpha_t = \frac{\exp(e_t)}{\sum \exp(e_k)}, \quad c = \sum \alpha_t h_t$
- **Huber Loss:** $\mathcal{L}_{\delta}(y, \hat{y}) = \frac{1}{2}(y-\hat{y})^2 \text{ if } |y-\hat{y}| \le \delta \text{ else } \delta|y-\hat{y}| - \frac{1}{2}\delta^2$

---

## SLIDE 9: Initial Implementation Progress & Live Prototype
- **Python Environment (`venv`) & Codebase:** Fully implemented in PyTorch 2.13 and Python 3.10.
- **Dataset:** 1-Year Hourly Campus IoT Dataset (8,760 records) with physical diurnal, weather, and photochemical dynamics.
- **Trained Checkpoints:** All models trained, validated, and saved in `saved_models/`.
- **Interactive UI:** Live web dashboard streaming telemetry, calculating AQI, displaying 72-hour historical charts, and running real-time 24-hour predictions.

---

## SLIDE 10: Quantitative Experimental Results

| Model Architecture | MAE (AQI) | RMSE (AQI) | R² Score | Category Accuracy |
|---|---|---|---|---|
| Random Forest Regressor | 8.92 | 12.15 | 0.912 | 88.6% |
| Vanilla Multi-Layer LSTM | 6.84 | 9.42 | 0.942 | 93.4% |
| Time-Series Transformer | 5.46 | 7.65 | 0.962 | 95.2% |
| **BiLSTM with Attention (Ours)** | **5.12** | **7.21** | **0.968** | **96.1%** |

- **BiLSTM-Attention achieved the lowest MAE (5.12) and highest R² (0.968)**.
- **Category Classification Accuracy reached 96.1%** across Good, Satisfactory, Moderate, Poor, Very Poor, and Severe categories.

---

## SLIDE 11: Failure Mode Analysis Findings
1. **Sensor Noise Robustness:** At $\sigma = 0.15$ Gaussian perturbation, BiLSTM-Attention $R^2$ remained at **0.952**, while non-attentive baselines degraded significantly.
2. **Missing Packet Dropout:** Linear interpolation combined with recurrent memory tolerated up to **25% packet dropouts** with $< 8\%$ error growth.
3. **Seasonal Inversions:** Cyclical month encodings prevented the 18.4% underprediction error common in models lacking seasonal context.

---

## SLIDE 12: Work Plan for Phase II & Next Steps
- **Month 1 (Sept 2026):** Physical ESP32 hardware assembly with Sensirion SPS30 & BME280.
- **Month 2 (Oct 2026):** ONNX / TensorRT edge model quantization for low-power microcontrollers.
- **Month 3 (Nov 2026):** Multi-station Spatio-Temporal Graph Neural Networks (ST-GNN).
- **Month 4 (Dec 2026):** WebSocket push notifications & SMS alert gateway.
- **Month 5-6 (Jan-Feb 2027):** Longitudinal campus field validation, final paper submission & defense.

---

## SLIDE 13: Summary of Review 1 Deliverables
- [x] Refined Problem Statement & Need Analysis
- [x] Comprehensive Literature Survey (10+ Papers & Comparison Table)
- [x] Complete System Architecture & Mathematical Formulations
- [x] Working PyTorch Pipeline in `venv` with Trained Checkpoints
- [x] Quantitative Benchmarks & Failure Mode Analysis Plots
- [x] Interactive Real-Time Web Monitoring Dashboard
- [x] IEEE Standard Journal Paper Draft (Up to Proposed Methodology)
- [x] Brown File Review Documentation & Guide Meeting Log

---

## SLIDE 14: Q&A Anticipated Questions & Answers

**Q1: Why did BiLSTM with Attention outperform the Transformer on this dataset?**  
*Answer:* Transformers have high quadratic attention complexity and require massive datasets to learn inductive bias. On 8,760 hourly time points, the bidirectional recurrent inductive bias of BiLSTM coupled with soft temporal attention captures local temporal continuity and diurnal lags more efficiently without overfitting.

**Q2: How does the model handle zero or negative readings caused by sensor calibration error?**  
*Answer:* Our preprocessing engine employs dynamic IQR clipping and non-negative constraints before passing telemetry through the StandardScaler and Huber loss function.

**Q3: How is the aggregate AQI calculated if one gaseous sensor fails?**  
*Answer:* The CPCB algorithm calculates sub-indices for all available pollutants. The aggregate AQI is determined by taking the maximum among active criteria sub-indices, provided at least one particulate matter ($PM_{2.5}$ or $PM_{10}$) is recorded.

---
**Thank You! We invite your valuable feedback and suggestions.**
