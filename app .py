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
