import streamlit as st
import math

st.set_page_config(page_title="Fluent TUI Gen", page_icon="🌬️", layout="wide")

# --- Funções de Física ---
def calc_reynolds(velocity, length, density, viscosity):
    if viscosity <= 0: return 0
    return (density * velocity * length) / viscosity

def calc_friction_velocity(velocity, length, density, viscosity):
    if viscosity <= 0 or density <= 0 or velocity <= 0 or length <= 0: return 1e-6
    Re = calc_reynolds(velocity, length, density, viscosity)
    if Re <= 0: return 1e-6
    Cf = 0.058 * math.pow(Re, -0.2)
    tau_w = 0.5 * density * math.pow(velocity, 2) * Cf
    return math.sqrt(tau_w / density)

def calc_yplus_from_height(height, u_tau, density, viscosity):
    if viscosity <= 0: return 0
    return (density * u_tau * height) / viscosity

def calc_height_from_yplus(yplus, u_tau, density, viscosity):
    if density <= 0 or u_tau <= 0: return 0
    return (yplus * viscosity) / (density * u_tau)

# --- App Layout ---
st.title("🌬️ Fluent TUI Gen (Streamlit Version)")
st.write("Gerador de scripts TUI automáticos para simulações aerodinâmicas.")

col_form, col_output = st.columns([1.1, 1])

# Initial States
if 'cell_height' not in st.session_state: st.session_state.cell_height = 1e-5
if 'y_plus' not in st.session_state: st.session_state.y_plus = 1.0
if 'time_step' not in st.session_state: st.session_state.time_step = 0.001

with col_form:
    with st.container(border=True):
        st.subheader("Geometria e Regime")
        geom_type = st.selectbox("Geometria", ["2d_airfoil", "3d_airfoil", "3d_wing"])
        regime = st.radio("Regime", ["steady", "transient"], horizontal=True)
        symmetry = st.checkbox("Malha possui Plano de Simetria") if "3d" in geom_type else False

    with st.container(border=True):
        st.subheader("Nomes das Fronteiras (Boundaries)")
        c_b1, c_b2 = st.columns(2)
        b_inlet = c_b1.text_input("Inlet", "inlet")
        b_outlet = c_b2.text_input("Outlet", "outlet")
        b_wall = c_b1.text_input("Parede (Asa/Perfil)", "wing-surface")
        b_sym = c_b2.text_input("Simetria", "symmetry-plane") if symmetry else ""

    with st.container(border=True):
        st.subheader("Cinemática e Propriedades do Ar")
        c_v1, c_v2 = st.columns(2)
        vel = c_v1.number_input("Velocidade (m/s)", value=50.0)
        aoa = c_v2.number_input("Ângulo de Ataque (°)", value=0.0, step=0.5)
        ref_area = c_v1.number_input("Área Ref. (m²)", value=1.0)
        ref_length = c_v2.number_input("Corda Ref. (m)", value=1.0)
        density = c_v1.number_input("Densidade (kg/m³)", value=1.225, format="%.4f")
        viscosity = c_v2.number_input("Viscosidade (kg/m.s)", value=1.7894e-5, format="%.2e")

    with st.container(border=True):
        st.subheader("Turbulência e Malha Fina (Y+)")
        turb_model = st.selectbox("Modelo", ["k-omega-sst", "spalart-allmaras", "k-epsilon-realizable"])
        
        u_tau = calc_friction_velocity(vel, ref_length, density, viscosity)
        
        def on_height_change():
            st.session_state.y_plus = calc_yplus_from_height(st.session_state.cell_height, u_tau, density, viscosity)
            
        def on_yplus_change():
            st.session_state.cell_height = calc_height_from_yplus(st.session_state.y_plus, u_tau, density, viscosity)

        st.caption("Ajuste iterativo: Alterar um atualiza o outro instantaneamente.")
        c_y1, c_y2 = st.columns(2)
        yplus_val = c_y1.number_input("Y+ Desejado/Atual", key="y_plus", on_change=on_yplus_change, step=0.1)
        height_val = c_y2.number_input("Altura 1ª Célula (m)", key="cell_height", format="%.2e", on_change=on_height_change)

    with st.container(border=True):
        st.subheader("Configuração Numérica")
        
        if regime == 'transient':
            c_tr1, c_tr2, c_tr3 = st.columns(3)
            cfl = c_tr1.number_input("CFL Alvo", value=1.0, step=0.1)
            mesh_sz = c_tr2.number_input("Célula Média (m)", value=0.01)
            
            c_tr3.number_input("Time Step (s)", key="time_step", format="%.2e")
            if st.button("Calcular Time-Step via CFL"):
                if vel > 0:
                    st.session_state.time_step = (cfl * mesh_sz) / vel
                    st.rerun()
                    
            c_t1, c_t2 = st.columns(2)
            tr_steps = c_t1.number_input("Num Time-Steps", value=500)
            tr_iters = c_t2.number_input("Max Iters/Step", value=20)
        else:
            steady_iters = st.number_input("Número Máx de Iterações", value=1000, step=100)

        st.markdown("**Critérios de Convergência (Resíduos)**")
        c_r1, c_r2, c_r3 = st.columns(3)
        r_cont = c_r1.number_input("Continuidade", value=1e-4, format="%.1e")
        r_vel = c_r2.number_input("Velocidade", value=1e-5, format="%.1e")
        
        if turb_model == "spalart-allmaras":
            r_nut = c_r3.number_input("nut", value=1e-4, format="%.1e")
        else:
            r_k = c_r3.number_input("k", value=1e-4, format="%.1e")
            r_omega = c_r1.number_input("omega / epsilon", value=1e-4, format="%.1e")


# --- Builder do TUI Script ---
aoa_rad = aoa * math.pi / 180
vx = vel * math.cos(aoa_rad)
vy = vel * math.sin(aoa_rad)

lines = [
    "; ====== Ansys Fluent TUI Setup Script ======",
    "; Generated automatically based on Aerodynamics parameters",
    f"; Regime: {regime.upper()}",
    "",
    "; --- 1. DEFINIÇÃO DE MODELOS FÍSICOS E DE TEMPO ---",
    "; Neste bloco é definido se a simulação é transiente ou permanente,",
    "; e qual será o modelo de turbulência utilizado."
]

if regime == "transient":
    lines.append("/define/models/unsteady-2nd-order yes")
else:
    lines.append("/define/models/unsteady-2nd-order no")
    lines.append("/define/models/steady yes")

if turb_model == "spalart-allmaras":
    lines.append("/define/models/viscous/spalart-allmaras yes")
elif turb_model == "k-omega-sst":
    lines.append("/define/models/viscous/kw-sst yes")
elif turb_model == "k-epsilon-realizable":
    lines.append("/define/models/viscous/ke-realizable yes")
    lines.append("/define/models/viscous/near-wall-treatment/enhanced-wall-treatment yes")

lines.append("")
lines.append("; --- 2. MATERIAIS - PROPRIEDADES DO FLUIDO ---")
lines.append("; Cria ou atualiza as propriedades físicas do 'air' (ar)")
lines.append(f"; Densidade: {density:.4e} kg/m³ | Viscosidade: {viscosity:.4e} kg/m.s")
lines.append(f"/define/materials/change-create air air yes constant {density:.4e} no no yes constant {viscosity:.4e} no no no")

lines.append("")
lines.append("; --- 3. CONDIÇÕES DE FRONTEIRA E CINEMÁTICA ---")
lines.append(f"; Fronteira definida como Inlet: '{b_inlet}'")
lines.append(f"; Componente U: {vx:.6f} m/s | Componente V: {vy:.6f} m/s")

if geom_type == "2d_airfoil":
    lines.append(f"/define/boundary-conditions/velocity-inlet {b_inlet} no no yes yes no {vx:.6f} no 0 no {vy:.6f}")
else:
    lines.append(f"/define/boundary-conditions/velocity-inlet {b_inlet} no no yes yes no {vx:.6f} no 0 no {vy:.6f} no 0")

if "3d" in geom_type and symmetry:
    lines.append("")
    lines.append(f"; Nota: Certifique-se de que a fronteira '{b_sym}' está configurada como 'symmetry'.")

lines.append("")
lines.append("; --- 4. VALORES DE REFERÊNCIA ---")
lines.append(f"; Fronteira usada para referência inicial: '{b_inlet}'")
if symmetry:
    lines.append("; ATENÇÃO: Simetria ativada. A Área de Ref. deveria representar METADE no caso simétrico.")
lines.append(f"/solve/reference-values/compute/{b_inlet}")
lines.append(f"/solve/reference-values/area {ref_area:.6f}")
lines.append(f"/solve/reference-values/length {ref_length:.6f}")
lines.append(f"/solve/reference-values/velocity {vel:.6f}")
lines.append(f"/solve/reference-values/density {density:.4e}")
lines.append(f"/solve/reference-values/viscosity {viscosity:.4e}")

lines.append("")
lines.append("; --- 5. MONITORES E REPORTS (LIFT E DRAG) ---")
lines.append(f"; Fronteira definida como Parede (Asa/Perfil): '{b_wall}'")
dx = math.cos(aoa_rad)
dy = math.sin(aoa_rad)
lx = -math.sin(aoa_rad)
ly = math.cos(aoa_rad)
lines.append(f"; Vetor de Arrasto (Drag): ({dx:.6f}, {dy:.6f}, 0)")
lines.append(f"; Vetor de Sustentação (Lift): ({lx:.6f}, {ly:.6f}, 0)")

lines.append(f"/solve/report-definitions/add drag-coef drag force-vector {dx:.6f} {dy:.6f} 0 scaled? yes thread-names \"{b_wall}\" ()")
lines.append(f"/solve/report-definitions/add lift-coef lift force-vector {lx:.6f} {ly:.6f} 0 scaled? yes thread-names \"{b_wall}\" ()")
lines.append(f"/solve/report-definitions/add drag-force drag force-vector {dx:.6f} {dy:.6f} 0 scaled? no thread-names \"{b_wall}\" ()")
lines.append(f"/solve/report-definitions/add lift-force lift force-vector {lx:.6f} {ly:.6f} 0 scaled? no thread-names \"{b_wall}\" ()")

lines.append("/solve/report-plots/add plot-coefs report-defs drag-coef lift-coef () print? yes active? yes window 1")
lines.append("/solve/report-plots/add plot-forces report-defs drag-force lift-force () print? yes active? yes window 2")

if regime == "transient":
    lines.append("/solve/report-plots/edit plot-coefs frequency-of time-step ()")
    lines.append("/solve/report-plots/edit plot-forces frequency-of time-step ()")

lines.append("")
lines.append("; --- 6. CRITÉRIOS DE CONVERGÊNCIA (RESIDUALS) ---")
if turb_model == "spalart-allmaras":
    res_str = f"{r_cont} {r_vel} {r_vel}" + (f" {r_vel}" if "3d" in geom_type else "") + f" {r_nut}"
    lines.append(f"/solve/monitors/residual/convergence-criteria {res_str}")
elif turb_model == "k-omega-sst" or turb_model == "k-epsilon-realizable":
    res_str = f"{r_cont} {r_vel} {r_vel}" + (f" {r_vel}" if "3d" in geom_type else "") + f" {r_k} {r_omega}"
    lines.append(f"/solve/monitors/residual/convergence-criteria {res_str}")

lines.append("")
lines.append("; --- 7. INICIALIZAÇÃO DO SOLVER ---")
if regime == "transient":
    lines.append("; Inicialização Padrão (Standard) recomendada para transiente")
    lines.append(f"/solve/initialize/compute-defaults/{b_inlet}")
    lines.append("/solve/initialize/initialize-flow")
else:
    lines.append("; Inicialização Híbrida (Hybrid) recomendada para permanente")
    lines.append("/solve/initialize/hyb-initialization")

lines.append("")
lines.append("; --- 8. CONTROLES DE SOLUÇÃO E EXECUÇÃO ---")
if regime == "transient":
    lines.append(f"; Passo de Tempo (Time-Step): {st.session_state.time_step:.6f} s")
    lines.append(f"/solve/set/time-step {st.session_state.time_step:.6e}")
    lines.append(f"/solve/set/max-iterations-per-time-step {tr_iters}")
    lines.append("")
    lines.append("; Executando cálculo transiente automaticamente:")
    lines.append(f"/solve/dual-time-iterate {tr_steps} {tr_iters}")
else:
    lines.append("; Executando cálculo permanente automaticamente:")
    lines.append(f"/solve/iterate {steady_iters}")

lines.append("")
lines.append("; --- FIM DO SCRIPT AUTOMATIZADO ---")

final_script = "\n".join(lines)

with col_output:
    st.subheader("📋 Script TUI Gerado")
    st.code(final_script, language="fluent")
