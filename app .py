import io
import hashlib
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st

from evaluador import evaluar


st.set_page_config(page_title="Evaluador ECA de Aguas", page_icon="💧", layout="wide")
st.title("💧 Evaluador ECA de Aguas")
st.caption("Comparación de resultados de agua por muestra y subcategoría con los límites ECA")

BASE = Path(__file__).parent / "ECA_Agua_2017_vs_Alcance_Chalaca_PowerBI.xlsx"
NECESARIAS = {"Categoría ECA", "Subcategoría", "Descripción subcategoría", "Tipo de parámetro",
              "Parámetro ECA", "Límite / criterio ECA", "Unidad ECA", "Tipo de criterio", "Línea de fuente"}


@st.cache_data
def cargar_excel(contenido):
    tabla = pd.read_excel(io.BytesIO(contenido), sheet_name="ECA_PowerBI", dtype={"Subcategoría": str})
    faltantes = NECESARIAS - set(tabla.columns)
    if faltantes:
        raise ValueError("Faltan columnas en ECA_PowerBI: " + ", ".join(sorted(faltantes)))
    tabla = tabla.dropna(subset=["Subcategoría", "Parámetro ECA"]).fillna("").copy()
    tabla["ID"] = tabla["Subcategoría"].astype(str) + "_" + tabla["Línea de fuente"].astype(str)
    if not tabla["ID"].is_unique:
        raise ValueError("Hay identificadores de parámetros duplicados en el Excel.")
    tabla["Área"] = tabla["Tipo de parámetro"].map(
        lambda t: "Microbiología" if t in ("Microbiológico", "Parasitológico")
        else "Hidrobiología" if t == "Hidrobiológico" else "Fisicoquímica")
    return tabla


with st.sidebar:
    st.header("Base ECA")
    archivo = st.file_uploader("Cargar Excel actualizado (opcional)", type=["xlsx"])
    st.caption("La aplicación usa su Excel incorporado si no cargas uno nuevo.")
    st.caption("Aquí se carga la tabla de límites ECA; los resultados se cargan en la sección Carga masiva.")

if archivo is not None:
    datos = archivo.getvalue()
elif BASE.exists():
    datos = BASE.read_bytes()
else:
    st.info("Carga el Excel ECA desde el panel lateral para comenzar.")
    st.stop()

try:
    eca = cargar_excel(datos)
except Exception as error:
    st.error(f"No se pudo leer el Excel: {error}")
    st.stop()

huella = hashlib.sha256(datos).hexdigest()[:12]
if st.session_state.get("huella") != huella:
    st.session_state["huella"] = huella
    st.session_state["resultados"] = {}
    st.session_state["ultimo_reporte"] = None


def limpiar_clave(valor):
    valor = unicodedata.normalize("NFD", str(valor).strip().casefold())
    return " ".join("".join(c for c in valor if unicodedata.category(c) != "Mn").split())


def comparar_archivo_resultados(tabla, base):
    obligatorias = {"Muestra", "Subcategoría", "Parámetro", "Resultado", "Unidad"}
    faltantes = obligatorias - set(tabla.columns)
    if faltantes:
        raise ValueError("Faltan columnas: " + ", ".join(sorted(faltantes)))
    tabla = tabla.fillna("")
    indice = {}
    for _, fila in base.iterrows():
        clave = (limpiar_clave(fila["Subcategoría"]), limpiar_clave(fila["Parámetro ECA"]))
        indice.setdefault(clave, []).append(fila)
    salida = []
    for posicion, r in tabla.iterrows():
        if not any(str(v).strip() for v in r.values):
            continue
        muestra = str(r["Muestra"]).strip()
        subcat = str(r["Subcategoría"]).strip()
        parametro = str(r["Parámetro"]).strip()
        resultado = str(r["Resultado"]).strip()
        unidad = str(r["Unidad"]).strip()
        registro = {"Fila Excel": posicion + 2, "Muestra": muestra, "Subcategoría": subcat,
                    "Parámetro": parametro, "Resultado": resultado, "Unidad": unidad,
                    "Categoría ECA": "", "Área": "", "Límite ECA": "", "Unidad ECA": ""}
        if not all([muestra, subcat, parametro, resultado, unidad]):
            estado, detalle = "NO EVALUABLE", "Completa muestra, subcategoría, parámetro, resultado y unidad."
        else:
            candidatos = indice.get((limpiar_clave(subcat), limpiar_clave(parametro)), [])
            categoria = str(r.get("Categoría ECA", "")).strip()
            if categoria:
                candidatos = [f for f in candidatos if limpiar_clave(f["Categoría ECA"]) == limpiar_clave(categoria)]
            if len(candidatos) == 0:
                estado, detalle = "NO EVALUABLE", "No se encontró este parámetro y subcategoría en la base ECA. Revisa su escritura."
            elif len(candidatos) > 1:
                estado, detalle = "NO EVALUABLE", "Hay varios límites ECA para este nombre. Especifica el ID ECA (columna opcional) o revisa la base."
                id_eca = str(r.get("ID ECA", "")).strip()
                if id_eca:
                    candidatos = [f for f in candidatos if str(f["ID"]).strip() == id_eca]
                    if len(candidatos) == 1:
                        estado = ""
            else:
                estado = ""
            if len(candidatos) == 1 and estado == "":
                f = candidatos[0]
                registro.update({"Categoría ECA": f["Categoría ECA"], "Área": f["Área"],
                                 "Límite ECA": f["Límite / criterio ECA"], "Unidad ECA": f["Unidad ECA"]})
                estado, detalle = evaluar(f, resultado, unidad,
                                           str(r.get("Promedio", "")).strip(),
                                           str(r.get("Área C1", "")).strip())
        registro.update({"Evaluación": estado, "Detalle": detalle})
        salida.append(registro)
    return pd.DataFrame(salida)


st.header("📄 Carga masiva de resultados")
with st.expander("Subir Excel o CSV con varias muestras y parámetros", expanded=True):
    st.write("Usa la hoja **Resultados** de la plantilla. Una fila representa un resultado; puedes incluir varias muestras y parámetros.")
    st.caption("Columnas obligatorias: Muestra, Subcategoría, Parámetro, Resultado y Unidad. Opcionales: Categoría ECA, Promedio, Área C1 e ID ECA.")
    resultados_subidos = st.file_uploader("Excel de resultados", type=["xlsx", "csv"], key="resultados_masivos")
    if resultados_subidos is not None:
        try:
            if resultados_subidos.name.lower().endswith(".csv"):
                cargados = pd.read_csv(io.BytesIO(resultados_subidos.getvalue()), sep=None, engine="python", dtype=str, keep_default_na=False)
            else:
                cargados = pd.read_excel(io.BytesIO(resultados_subidos.getvalue()), sheet_name="Resultados", dtype=str, keep_default_na=False)
            reporte_masivo = comparar_archivo_resultados(cargados, eca)
            if reporte_masivo.empty:
                st.warning("El archivo no contiene resultados para evaluar.")
            else:
                st.success(f"Se procesaron {len(reporte_masivo)} resultados de {reporte_masivo['Muestra'].nunique()} muestras.")
                conteos = reporte_masivo.groupby("Muestra", dropna=False)["Evaluación"].agg(list)
                resumen = pd.DataFrame([{"Muestra": m, "Estado de la muestra":
                    "NO CUMPLE" if "NO CUMPLE" in estados else
                    "REVISAR" if any(e != "CUMPLE" for e in estados) else "CUMPLE",
                    "Cumplen": estados.count("CUMPLE"), "No cumplen": estados.count("NO CUMPLE"),
                    "Por revisar": sum(e not in ("CUMPLE", "NO CUMPLE") for e in estados)}
                    for m, estados in conteos.items()])
                st.subheader("Estado por muestra")
                st.dataframe(resumen, hide_index=True, use_container_width=True)
                st.subheader("Detalle de resultados")
                st.dataframe(reporte_masivo, hide_index=True, use_container_width=True, height=400)
                st.download_button("⬇️ Descargar evaluación CSV", reporte_masivo.to_csv(index=False, sep=";").encode("utf-8-sig"),
                                   file_name="Evaluacion_masiva_ECA_aguas.csv", mime="text/csv")
                st.caption("REVISAR incluye resultados incompletos, parámetros sin coincidencia y criterios que requieren interpretación.")
        except Exception as error:
            st.error(f"No se pudo procesar el archivo de resultados: {error}")

st.divider()
st.header("Ingreso manual")

izq, der = st.columns(2)
with izq:
    muestra = st.text_input("Identificación de la muestra", "M-001").strip()
    categoria = st.selectbox("Categoría ECA", eca["Categoría ECA"].drop_duplicates().tolist())
with der:
    modo = st.radio("Modo de ingreso", ["Un parámetro", "Varios parámetros"], horizontal=True)
    area = st.selectbox("Área", ["Conjunto", "Microbiología", "Fisicoquímica", "Hidrobiología"])

sub = eca[eca["Categoría ECA"] == categoria]
codigos = sub["Subcategoría"].drop_duplicates().tolist()
codigo = st.selectbox("Subcategoría", codigos,
    format_func=lambda c: f'{c} — {sub.loc[sub["Subcategoría"] == c, "Descripción subcategoría"].iloc[0]}')
area_c1 = st.selectbox("Tipo de área C1 (si corresponde)", ["Seleccione", "Aprobada", "Restringida"])

filas = eca[eca["Subcategoría"] == codigo].copy()
if area != "Conjunto":
    filas = filas[filas["Área"] == area].copy()
if filas.empty:
    st.warning("No hay parámetros para esta selección.")
    st.stop()

def texto(x):
    return "" if pd.isna(x) else str(x)

def formatear(f):
    return f'{f["Parámetro ECA"]}  |  ECA: {f["Límite / criterio ECA"]} {f["Unidad ECA"]}'

clave = f"{muestra}|{codigo}"
registro = st.session_state["resultados"].get(clave, {})

with st.form("ingreso_eca"):
    if modo == "Un parámetro":
        opciones = filas["ID"].tolist()
        indice = {id_: filas.loc[filas["ID"] == id_].iloc[0] for id_ in opciones}
        seleccionado = st.selectbox("Parámetro", opciones, format_func=lambda id_: formatear(indice[id_]))
        fila = indice[seleccionado]
        anterior = registro.get(seleccionado, {})
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            resultado = st.text_input("Resultado", value=anterior.get("Resultado", ""),
                                      placeholder="Ej.: 15; <1,8; Ausencia")
        with col2:
            unidad = st.text_input("Unidad", value=anterior.get("Unidad", texto(fila["Unidad ECA"])))
        with col3:
            promedio = st.text_input("Promedio para Δ", value=anterior.get("Promedio", ""))
        carga = None
    else:
        st.write("**Escribe los resultados que deseas evaluar.** Deja los demás vacíos.")
        st.caption("Puedes buscar un parámetro y mantener los resultados guardados para esta muestra al cambiar el filtro.")
        busqueda = st.text_input("Buscar parámetro (opcional)")
        visibles = filas[filas["Parámetro ECA"].astype(str).str.contains(busqueda, case=False, regex=False)] if busqueda else filas
        carga = pd.DataFrame([{
            "ID": f["ID"], "Área": f["Área"], "Parámetro": f["Parámetro ECA"],
            "Límite ECA": texto(f["Límite / criterio ECA"]),
            "Resultado": registro.get(f["ID"], {}).get("Resultado", ""),
            "Unidad": registro.get(f["ID"], {}).get("Unidad", texto(f["Unidad ECA"])),
            "Promedio": registro.get(f["ID"], {}).get("Promedio", "")
        } for _, f in visibles.iterrows()])
        editor = st.data_editor(carga, hide_index=True, width="stretch", height=500,
            disabled=["ID", "Área", "Parámetro", "Límite ECA"],
            column_config={
                "ID": None,
                "Área": st.column_config.TextColumn("Área", width="medium"),
                "Parámetro": st.column_config.TextColumn("Parámetro", width="large"),
                "Límite ECA": st.column_config.TextColumn("Límite ECA", width="medium"),
                "Resultado": st.column_config.TextColumn("Resultado", width="medium"),
                "Unidad": st.column_config.TextColumn("Unidad", width="medium"),
                "Promedio": st.column_config.TextColumn("Promedio Δ", width="medium"),
            }, key=f"editor_{huella}_{clave}_{area}_{busqueda}")
    enviado = st.form_submit_button("EVALUAR RESULTADOS", type="primary", use_container_width=True)

if enviado:
    if not muestra:
        st.error("Ingresa la identificación de la muestra.")
    else:
        if modo == "Un parámetro":
            if resultado.strip():
                registro[seleccionado] = {"Resultado": resultado.strip(), "Unidad": unidad.strip(),
                                         "Promedio": promedio.strip()}
            else:
                registro.pop(seleccionado, None)
        else:
            for _, r in editor.iterrows():
                id_ = r["ID"]
                if texto(r["Resultado"]).strip():
                    registro[id_] = {"Resultado": texto(r["Resultado"]).strip(),
                                     "Unidad": texto(r["Unidad"]).strip(),
                                     "Promedio": texto(r["Promedio"]).strip()}
                else:
                    registro.pop(id_, None)
        st.session_state["resultados"][clave] = registro
        ids = [seleccionado] if modo == "Un parámetro" else filas["ID"].tolist()
        reporte = []
        for id_ in ids:
            if id_ not in registro:
                continue
            f = filas.loc[filas["ID"] == id_].iloc[0]
            r = registro[id_]
            estado, detalle = evaluar(f, r["Resultado"], r["Unidad"], r["Promedio"], area_c1)
            reporte.append({"Muestra": muestra, "Categoría ECA": categoria,
                "Subcategoría": codigo, "Área": f["Área"], "Parámetro": f["Parámetro ECA"],
                "Resultado": r["Resultado"], "Unidad": r["Unidad"],
                "Límite ECA": f["Límite / criterio ECA"], "Unidad ECA": f["Unidad ECA"],
                "Evaluación": estado, "Detalle": detalle})
        st.session_state["ultimo_reporte"] = pd.DataFrame(reporte)
        st.session_state["contexto_reporte"] = (muestra, codigo, area, modo)

reporte = st.session_state.get("ultimo_reporte")
if reporte is not None and not reporte.empty:
    contexto = (muestra, codigo, area, modo)
    if st.session_state.get("contexto_reporte") == contexto:
        if (reporte["Evaluación"] == "NO CUMPLE").any():
            color, global_estado = "#b42318", "NO CUMPLE"
        elif (reporte["Evaluación"] != "CUMPLE").any():
            color, global_estado = "#b54708", "REVISAR"
        else:
            color, global_estado = "#027a48", "CUMPLE"
        st.markdown(f'<div style="background:{color};color:white;padding:18px;'
                    f'border-radius:12px;font-size:26px;font-weight:800">'
                    f'RESULTADO DE LA MUESTRA: {global_estado}</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("CUMPLEN", int((reporte["Evaluación"] == "CUMPLE").sum()))
        c2.metric("NO CUMPLEN", int((reporte["Evaluación"] == "NO CUMPLE").sum()))
        c3.metric("POR REVISAR", int((reporte["Evaluación"] == "NO EVALUABLE").sum()))
        st.dataframe(reporte, hide_index=True, width="stretch", height=420)
        st.download_button("⬇️ Descargar reporte CSV", data=reporte.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name=f"ECA_Aguas_{muestra}_{codigo}.csv", mime="text/csv")
        st.caption("Se dictaminaron únicamente los parámetros con resultado. REVISAR indica que faltan datos o se requiere interpretar el criterio ECA.")
elif enviado and (reporte is None or reporte.empty):
    st.warning("Ingresa al menos un resultado antes de evaluar.")
