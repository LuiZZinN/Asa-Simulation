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

# --- Funções de Script de Malha e Geometria ---
def generate_geom_script(geom_tool, geom_type, airfoil_coords, domain_radius, domain_wake, ref_length):
    is_2d = (geom_type == '2d_airfoil')
    
    # Scale coordinates
    lines_coords = airfoil_coords.strip().split('\n')
    scaled_lines = []
    for line in lines_coords:
        parts = line.split()
        if len(parts) >= 2:
            try:
                x = float(parts[0]) * ref_length
                y = float(parts[1]) * ref_length
                scaled_lines.append(f"{x:.6f} {y:.6f}")
            except ValueError:
                pass
    scaled_coords_sc = "\n".join(scaled_lines)
    scaled_coords_dm = "\\n".join(scaled_lines)

    if geom_tool == 'spaceclaim':
        s = f"""# -*- coding: utf-8 -*-
# =====================================================================
# SpaceClaim Python Script (Ansys V19+)
# Para: {'Perfil 2D Sectionado (Retangular)' if is_2d else 'Perfil 3D Extrudado (Domínio Contínuo)'}
# Instruções: No SpaceClaim, abra a aba "File" -> "Scripting" (ou "Design" -> "Scripting" em versões mais novas),
# cole este código e clique em Run Script.
# =====================================================================

import math

ClearAll()

# 1. Coordenadas do Perfil Aerodinâmico (Escalonadas para Corda = {ref_length} m)
coords_str = \"\"\"{scaled_coords_sc}\"\"\"
points = []
for line in coords_str.strip().split('\\n'):
    parts = line.split()
    if len(parts) >= 2:
        x, y = float(parts[0]), float(parts[1])
        # Assumindo coords já em metros (ou normalizadas), converte para a unidade base do SC se necessário
        points.append(Point2D.Create(x, y))

# 2. Criação da Curva do Perfil
if len(points) > 0:
    # Limpa ponto duplicado no final se o perfil já for fechado
    if abs(points[0].X - points[-1].X) < 1e-6 and abs(points[0].Y - points[-1].Y) < 1e-6:
        points = points[:-1]
        
    for i in range(len(points) - 1):
        SketchLine.Create(points[i], points[i+1])
    SketchLine.Create(points[-1], points[0])

# 3. Criação do Domínio Externo (Retangular)
radius = {domain_radius}
wake_length = {domain_wake}
print("Desenhando Dominio: Raio={{}}m, Esteira={{}}m".format(radius, wake_length))

"""
        if is_2d:
            s += """# -- METODOLOGIA 2D ESTRUTURADO (DOMÍNIO RETANGULAR COM SEÇÕES) --
# Adicionando as linhas de corte para possibilitar o Sizing com Bias na malha
# O script dividirá a face principal criando blocos (topologia estruturada)
print("No SpaceClaim 2D estruturado, o script desenha os cortes em H-Grid")
SketchLine.Create(Point2D.Create(-radius, radius), Point2D.Create(wake_length, radius))
SketchLine.Create(Point2D.Create(-radius, -radius), Point2D.Create(wake_length, -radius))
SketchLine.Create(Point2D.Create(wake_length, radius), Point2D.Create(wake_length, -radius))
# Reta de entrada frontal
SketchLine.Create(Point2D.Create(-radius, radius), Point2D.Create(-radius, -radius))

le_point = min(points, key=lambda p: p.X)
te_point = max(points, key=lambda p: p.X)
# Linhas de seccionamento H-Grid (Cortes da Asa para as Bordas)
SketchLine.Create(le_point, Point2D.Create(-radius, le_point.Y))
SketchLine.Create(le_point, Point2D.Create(le_point.X, radius))
SketchLine.Create(le_point, Point2D.Create(le_point.X, -radius))
SketchLine.Create(te_point, Point2D.Create(wake_length, te_point.Y))
SketchLine.Create(te_point, Point2D.Create(te_point.X, radius))
SketchLine.Create(te_point, Point2D.Create(te_point.X, -radius))

print("Tentando criar grupos (Named Selections) automaticamente...")
try:
    # Alterna para modo 3D (Solid) para gerar as faces e edges
    try:
        ViewHelper.SetViewMode(InteractionMode.Solid, None)
    except:
        ViewHelper.SetViewMode(InteractionMode.Solid)
        
    part = Window.ActiveWindow.Document.MainPart
    inlet_edges = []
    outlet_edges = []
    radiais_edges = []
    perfil_edges = []
    
    for e in part.Edges:
        box = e.BoundingBox
        if box.Min.X <= -radius + 1e-4 or box.Max.Y >= radius - 1e-4 or box.Min.Y <= -radius + 1e-4:
            inlet_edges.append(e)
        elif box.Max.X >= wake_length - 1e-4:
            outlet_edges.append(e)
        elif abs(box.Min.X - box.Max.X) < 1e-5 or abs(box.Min.Y - box.Max.Y) < 1e-5:
            radiais_edges.append(e)
        else:
            perfil_edges.append(e)
            
    if inlet_edges: Group.Create(Window.ActiveWindow.Document, "{b_inlet}", Selection.Create(inlet_edges))
    if outlet_edges: Group.Create(Window.ActiveWindow.Document, "{b_outlet}", Selection.Create(outlet_edges))
    if radiais_edges: Group.Create(Window.ActiveWindow.Document, "Radiais", Selection.Create(radiais_edges))
    if perfil_edges: Group.Create(Window.ActiveWindow.Document, "{b_wall}", Selection.Create(perfil_edges))
    print("Grupos nomeados com sucesso!")
except Exception as inst:
    print("Nao foi possivel criar grupos automaticamente:", inst)
"""
        else:
            s += """# -- METODOLOGIA 3D (Domínio Contínuo sem secções, resolvido via Inflation) --
# Perímetro contínuo do domíno fluido retangular
SketchLine.Create(Point2D.Create(-radius, radius), Point2D.Create(wake_length, radius))
SketchLine.Create(Point2D.Create(-radius, -radius), Point2D.Create(wake_length, -radius))
SketchLine.Create(Point2D.Create(wake_length, radius), Point2D.Create(wake_length, -radius))
SketchLine.Create(Point2D.Create(-radius, radius), Point2D.Create(-radius, -radius))

# Após formar a superfície, subtraia o perfil (Operação Combine/Cut) e use a ferramenta Pull (Extrude) com a Envergadura desejada.
"""
        s += """
# Alterna para o modo Sólido (3D) para preencher a face.
try:
    ViewHelper.SetViewMode(InteractionMode.Solid, None)
except:
    try:
        ViewHelper.SetViewMode(InteractionMode.Solid)
    except:
        print("Não foi possível alternar para o modo Solid automaticamente. Vá em 'Design' -> '3D Mode' para transformar os contornos em superfícies.")
"""
        return s
    
    elif geom_tool == 'design_modeler':
        s = f"""// =====================================================================
// Ansys DesignModeler JScript
// Para: {'Perfil 2D Sectionado (Retangular)' if is_2d else 'Perfil 3D Extrudado (Domínio Contínuo)'}
// Instruções: Salve como .js. No DesignModeler, vá em File -> Run Script.
// =====================================================================

// Coordenadas (Escalonadas para Corda = {ref_length} m)
var coords = "{scaled_coords_dm}";

// O script JScript para o DesignModeler é restrito. 
// Siga as instruções abaixo usando a interface gráfica:
agb.Print("================ INSTRUÇÕES DESIGNMODELER ================");
agb.Print("Para gerar o perfil e o domínio fluidodinâmico de forma robusta:");
agb.Print("1. Copie as coordenadas escalonadas do código (acima) e salve num arquivo 'perfil.txt'.");
agb.Print("2. No DM, vá em 'Create' -> '3D Curve' e aponte para o 'perfil.txt'.");
agb.Print("3. Transforme a curva num corpo de superfície com 'Concept' -> 'Surfaces from Edges'.");
agb.Print("4. Crie um Sketch no plano XY e desenhe as linhas do Domínio Retangular (raio/topo {domain_radius}m, esteira {domain_wake}m).");
agb.Print("5. Forme uma superfície do Domínio ('Concept' -> 'Surfaces from Sketches').");
agb.Print("6. Subtraia a asa do domínio ('Create' -> 'Boolean' ou 'Tools' -> 'Face Split').");
agb.Print("=====================================================");
"""
        return s
        
    return ""

def generate_mesh_script(mesh_tool, geom_type, first_cell_height, b_inlet, b_outlet, b_wall, b_sym):
  is_2d = (geom_type == '2d_airfoil')
  
  if mesh_tool == 'ansys_meshing':
      s = f"""# -*- coding: utf-8 -*-
# =====================================================================
# Ansys Meshing (Mechanical API) Script / Configuração Automática
# =====================================================================
import clr
try:
    clr.AddReference("System.Windows.Forms")
    import System.Windows.Forms as WinForms
    HAS_WINFORMS = True
except:
    HAS_WINFORMS = False

def msg_box(texto, titulo="Ansys Meshing Script"):
    if HAS_WINFORMS:
        WinForms.MessageBox.Show(texto, titulo)
    else:
        try:
            ExtAPI.Log.WriteMessage(texto)
        except:
            print(texto)

first_cell_height = {first_cell_height:.4e} # (m) garantindo Y+ alvo

try:
    mesh = ExtAPI.DataModel.Project.Model.Mesh
"""
      if is_2d:
          s += f"""
    # Funcoes auxiliares para localizar Named Selections vindas do SpaceClaim
    def get_ns(name):
        try:
            for ns in mesh.Parent.NamedSelections.Children:
                if ns.Name == name: return ns
        except: pass
        return None

    # Mapeamento e Sizing para 2D
    sz_perfil = mesh.AddSizing()
    sz_perfil.Name = "1. Airfoil Sizing (Extradador e Intrador)"
    ns_perfil = get_ns("{b_wall}")
    if ns_perfil: sz_perfil.Location = ns_perfil
    try:
        sz_perfil.Type = Ansys.Mechanical.DataModel.Enums.SizingType.NumberOfDivisions
        sz_perfil.NumberOfDivisions = 150
        sz_perfil.BiasOption = Ansys.Mechanical.DataModel.Enums.BiasOptionType.BiasFactor
        sz_perfil.BiasFactor = 50.0
    except:
        pass
    
    sz_radiais = mesh.AddSizing()
    sz_radiais.Name = "2. Farfield/Radias Sizing (Arestas de Corte)"
    ns_radiais = get_ns("Radiais")
    if ns_radiais: sz_radiais.Location = ns_radiais
    try:
        sz_radiais.Type = Ansys.Mechanical.DataModel.Enums.SizingType.NumberOfDivisions
        sz_radiais.NumberOfDivisions = 80
        sz_radiais.BiasOption = Ansys.Mechanical.DataModel.Enums.BiasOptionType.BiasFactor
        sz_radiais.BiasFactor = 100.0 # Ajuste para Y+
    except:
        pass
    
    fm = mesh.AddFaceMeshing()
    fm.Name = "3. Face Meshing (Selecionar a face do dominio principal)"

    texto = (
        "Os itens de Malha foram configurados na arvore! \\n\\n"
        "==== INSTRUCOES PARA GEOMETRIAS ====\\n"
        "1. Os Named Selections ('{b_inlet}', '{b_outlet}', '{b_wall}', 'Radiais') vieram do SpaceClaim.\\n"
        "2. Airfoil Sizing: Foi configurado para 150 divisoes com Bias Factor de 50. (Ajuste o comportamento do Bias.\\n"
        "3. Farfield/Radiais Sizing: Foi configurado para 80 divisoes. \\n"
        "   -> IMPORTANTE: Calcule o Bias Factor ou ajuste de forma que o tamanho do 1 elemento seja: {first_cell_height:.4e} m.\\n"
        "4. Face Meshing: Selecione a face principal 2D para Mapped Meshing.\\n"
    )
    msg_box(texto)
"""
      else:
          s += f"""
    # Named Selections 3D
    ns_in = mesh.Parent.AddNamedSelection()
    ns_in.Name = "{b_inlet} (Faces de entrada)"
    ns_out = mesh.Parent.AddNamedSelection()
    ns_out.Name = "{b_outlet} (Faces de saida)"
    ns_win = mesh.Parent.AddNamedSelection()
    ns_win.Name = "{b_wall} (Faces do perfil/asa)"
"""
          if "3d" in geom_type and b_sym:
              s += f"""    ns_sym = mesh.Parent.AddNamedSelection()
    ns_sym.Name = "{b_sym} (Plano de simetria)"
"""
          s += f"""
    # Inflation para 3D
    inf = mesh.AddInflation()
    inf.Name = "1. Inflation da Camada Limite"
    
    sz = mesh.AddSizing()
    sz.Name = "2. Sizing de Refinamento (Superficie ou Corpo)"
    
    texto = (
        "Os itens de malha e Named Selections foram criados na arvore! \\n\\n"
        "Agora atribua as geometrias correspondentes:\\n"
        "1. Named Selections: Selecione as faces para cada contorno.\\n"
        "2. Inflation: Selecione Volume fluido (Geometry) e Faces da Asa (Boundary).\\n"
        "   -> (First Layer Height: {first_cell_height:.4e} m)\\n"
        "3. Sizing: Refine o dominio se necessario.\\n"
    )
    msg_box(texto)
"""
      s += """
except Exception as e:
    msg_box("Erro ao gerar arvore de malha (execute na aba Mechanical): " + str(e))
"""
      return s
  
  elif mesh_tool == 'fluent_meshing':
      s = f"""; =====================================================================
; Fluent Meshing TUI Script
; =====================================================================
; OBS: O Fluent Meshing (Watertight Workflow) é idealizado primariamente
; para 3D não-estruturados com robusto motor de Prismas/Inflation.

"""
      if is_2d:
          s += """; ATENÇÃO: O Fluent Meshing aceita 2D, porém o Surface Meshing e Volume Meshing 
; nativo TUI funciona exponencialmente melhor se você mapear a placa 2D em 
; uma Z-Thickness muito fina e extrair o 2D final no solver Fluent padrão.

; No Fluent Solver (pós-malha): /mesh/modify-zones/make-2d

"""
      s += f"""; 1. Importação da Geometria Limpa
; Lembre-se de verificar as Unidades e o Tolerances do modelo!
/file/import/cad "domain.step" millimeter

; 2. Named Selections já devem vir da geometria, caso contrário renomeie via TUI:
; /boundary/rename-zone old-name {b_wall}

; 3. Configuração do Size Field (Refinamento da Superfície)
/mesh/size-field/create-sizing-parameters "asas" yes curvature 18 0.001 0.1 
; Substituir limites Global Min/Max de acordo com o CAD.

; 4. Criação do Scoped Prism (Camada Limite / Inflation)
; Tipo de Prisma: first-height para garantir o Y+
/mesh/scoped-prisms/create "camada-asa" 
/mesh/scoped-prisms/edit "camada-asa" first-height {first_cell_height:.4e} 15 1.2 "constant" "{b_wall}" ()

; 5. Geração e Preenchimento Poly-Hexcore
/mesh/surface-mesh/create yes
/mesh/volume-mesh/create poly-hexcore

; 6. Avaliação Qualidade
/mesh/check-quality

; 7. Escrever malha
/file/write-mesh "aerodynamics.msh"
"""
      return s
  
  return ""

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
        st.subheader("📦 Geometria e Malha (Pré-Processamento)")
        
        c_g1, c_g2 = st.columns(2)
        if geom_type != '3d_wing':
            geom_tool = c_g1.selectbox(
                "Gerador Geometria", 
                ["none", "spaceclaim", "design_modeler"], 
                format_func=lambda x: "Não gerar" if x == "none" else ("SpaceClaim (Python)" if x == "spaceclaim" else "DesignModeler (JScript)")
            )
        else:
            geom_tool = "none"

        mesh_options = ["none", "ansys_meshing", "fluent_meshing"] if geom_type != '3d_wing' else ["none", "fluent_meshing"]
        mesh_tool = c_g2.selectbox(
            "Gerador de Malha", 
            mesh_options, 
            format_func=lambda x: "Não gerar" if x == "none" else ("Ansys Meshing (Guia/ACT)" if x == "ansys_meshing" else "Fluent Meshing (TUI)")
        )
        
        if geom_type != '3d_wing' and (geom_tool != "none" or mesh_tool != "none"):
            c_dom1, c_dom2 = st.columns(2)
            domain_radius = c_dom1.number_input("Dist. Entrada / Topo (m)", value=10.0)
            domain_wake = c_dom2.number_input("Comprimento Esteira (m)", value=20.0)
            default_coords = "1.00000 0.00000\n0.95000 0.01300\n0.90000 0.02400\n0.80000 0.04300\n0.70000 0.05800\n0.60000 0.06800\n0.50000 0.07500\n0.40000 0.07800\n0.30000 0.07600\n0.20000 0.06800\n0.10000 0.04900\n0.05000 0.03400\n0.00000 0.00000\n0.05000 -0.01800\n0.10000 -0.02600\n0.20000 -0.03300\n0.30000 -0.03500\n0.40000 -0.03300\n0.50000 -0.02900\n0.60000 -0.02400\n0.70000 -0.01800\n0.80000 -0.01200\n0.90000 -0.00600\n0.95000 -0.00300\n1.00000 0.00000"
            airfoil_coords = st.text_area("Coordenadas do Perfil (X Y)", value=default_coords, height=150)
        else:
            domain_radius, domain_wake, airfoil_coords = 10.0, 20.0, ""

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

lines.append("; --- 3. CONDIÇÕES DE FRONTEIRA E CINEMÁTICA ---")
lines.append("; Aplica a Magnitude da velocidade e os componentes do vetor direção.")
lines.append(f"; Fronteira definida como Inlet: '{b_inlet}'")

# Vetor de direção
dx = math.cos(aoa_rad)
dy = math.sin(aoa_rad)

lines.append(f"; Velocidade Magnitude: {vel:.6f} m/s")

turb_suffix = ""
if turb_model != "spalart-allmaras":
    turb_suffix = " no 5 no 10"
    lines.append(f"; ATENÇÃO: Foi adicionado '{turb_suffix}' no final do comando de inlet para a turbulência (5% intensidade, 10 razão de visc).")
    lines.append("; Dependendo da sua versão do Fluent, a sequência de 'yes'/'no' para os perfis de turbulência pode mudar.")
    lines.append("; Caso o script trave perguntando 'Turbulent Specification Method', ajuste a sequência final da linha abaixo.")
else:
    turb_suffix = " no 10"

if geom_type == "2d_airfoil":
    lines.append(f"; Vetor Direção -> X (cos): {dx:.6f} | Y (sin): {dy:.6f}")
    lines.append(f"/define/boundary-conditions/velocity-inlet {b_inlet} magnitude-and-direction no {vel:.6f} no 0 no {dx:.6f} no {dy:.6f}{turb_suffix}")
else:
    lines.append(f"; Vetor Direção -> X (cos): {dx:.6f} | Y (sin): {dy:.6f} | Z: 0")
    lines.append(f"/define/boundary-conditions/velocity-inlet {b_inlet} magnitude-and-direction no {vel:.6f} no 0 no {dx:.6f} no {dy:.6f} no 0{turb_suffix}")

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
    st.subheader("📋 Scripts Gerados")
    
    active_tabs = ["Fluent TUI"]
    if geom_tool != "none": active_tabs.append("Geometria")
    if mesh_tool != "none": active_tabs.append("Malha")
    
    tabs = st.tabs(active_tabs)
    
    with tabs[0]:
        st.download_button(label="Baixar Script (.jou)", data=final_script, file_name="solver_setup.jou", mime="text/plain")
        st.code(final_script, language="fluent")
        st.info("Baixe o .jou e leia no Fluent (file/read-macro) ou copie e cole no console.")
        
    if geom_tool != "none":
        geom_idx = active_tabs.index("Geometria")
        with tabs[geom_idx]:
            geom_script = generate_geom_script(geom_tool, geom_type, airfoil_coords, domain_radius, domain_wake, ref_length)
            ext = ".py" if geom_tool == "spaceclaim" else ".js"
            st.download_button(label=f"Baixar Script ({ext})", data=geom_script, file_name=f"geom_setup{ext}", mime="text/plain")
            st.code(geom_script, language="python" if geom_tool == "spaceclaim" else "javascript")
            st.info("Abra a ferramenta selecionada e rode o script na aba Scripting.")
            
    if mesh_tool != "none":
        mesh_idx = active_tabs.index("Malha")
        with tabs[mesh_idx]:
            mesh_script = generate_mesh_script(mesh_tool, geom_type, height_val, b_inlet, b_outlet, b_wall, b_sym if symmetry else None)
            ext = ".py" if mesh_tool == "ansys_meshing" else ".jou"
            st.download_button(label=f"Baixar Script ({ext})", data=mesh_script, file_name=f"mesh_setup{ext}", mime="text/plain")
            st.code(mesh_script, language="python" if mesh_tool == "ansys_meshing" else "fluent")
            st.info("Use como guia ou rode no Fluent Meshing TUI para pre-processar a malha.")
