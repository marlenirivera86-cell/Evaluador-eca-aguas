import re
import unicodedata

def normalizar(txt):
    txt = ''.join(c for c in unicodedata.normalize('NFD', str(txt).strip().lower()) if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', '', txt).replace('µ', 'u').replace('μ', 'u').replace('º', '°')

def numero(txt):
    """Admite 0,5; 0.5; 1 000; 1.000,5. Rechaza intervalos y texto."""
    s = str(txt).strip().replace('\u00a0', ' ').replace(' ', '')
    if '.' in s and ',' in s and re.fullmatch(r'[-+]?\d{1,3}(?:\.\d{3})+(?:,\d+)?', s):
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '.')
    if not re.fullmatch(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)', s):
        raise ValueError(f'Número no interpretable: {txt}')
    return float(s)

def evaluar(fila, resultado, unidad='', promedio='', tipo_area=''):
    """Devuelve (estado, explicación). Evita dictaminar límites condicionados o unidades incompatibles."""
    v = str(resultado).strip()
    if not v:
        return 'SIN RESULTADO', 'Registra el resultado o desmarca Solicitado.'
    u_eca = str(fila['Unidad ECA']).strip()
    if not unidad or normalizar(unidad) != normalizar(u_eca):
        return 'NO EVALUABLE', f'Unidad distinta o ausente. ECA: {u_eca}; resultado: {unidad or "sin unidad"}. No se convierten UFC y NMP automáticamente.'
    criterio = str(fila['Límite / criterio ECA']).strip()
    param = str(fila['Parámetro ECA']).lower()
    if 'trihalometanos (suma' in param:
        return 'NO EVALUABLE', 'Calcular primero el índice: suma de cada concentración dividida entre su ECA individual.'
    if 'Tabla NH3' in criterio:
        return 'NO EVALUABLE', 'El ECA de NH3 depende del pH y la temperatura: consultar la tabla del anexo.'
    if 'área aprobada' in criterio:
        if tipo_area == 'Aprobada': criterio = '≤14'
        elif tipo_area == 'Restringida': criterio = '≤88'
        else: return 'NO EVALUABLE', 'En C1 indica si el área es aprobada o restringida.'
    if criterio.startswith(('Δ', '∆')):
        try:
            diferencia = abs(numero(v) - numero(promedio))
            maximo = numero(criterio[1:])
        except ValueError:
            return 'NO EVALUABLE', 'Ingresa un valor numérico y el promedio mensual multianual de referencia.'
        return ('CUMPLE' if diferencia <= maximo else 'NO CUMPLE',
                f'Variación absoluta {diferencia:g} °C respecto al promedio; máximo {maximo:g} °C.')
    c = normalizar(criterio); r = normalizar(v)
    if 'ausencia' in c or 'novisible' in c or 'sincambio' in c or 'aceptable' in c:
        if 'ausencia' in c:
            ok = r in ('ausencia', 'ausente', 'no detectado', 'nodetectado', '0')
            fail = r in ('presencia', 'presente', 'detectado', 'visible', 'peliculavisible', 'espumapersistente')
        elif 'novisible' in c:
            ok = r in ('novisible', 'ausencia', 'ausente');fail = r in ('visible', 'presencia', 'presente')
        elif 'sincambio' in c:
            ok = r in ('sincambio', 'sincambioanormal');fail = r in ('cambio', 'cambioanormal')
        else:
            ok = r == 'aceptable';fail = r in ('noaceptable', 'inaceptable')
        if ok:return 'CUMPLE', f'Criterio cualitativo: {criterio}.'
        if fail:return 'NO CUMPLE', f'Criterio cualitativo: {criterio}.'
        return 'NO EVALUABLE', f'Resultado cualitativo no reconocido para: {criterio}.'
    try:
        if '–' in criterio or re.search(r'\s+a\s+', criterio, re.I) or re.search(r'\d\s*-\s*\d', criterio):
            partes = re.split(r'\s*(?:–|—|\ba\b|-)\s*', criterio, maxsplit=1)
            minimo,maximo=map(numero,partes)
            actual=numero(v)
            return ('CUMPLE' if minimo<=actual<=maximo else 'NO CUMPLE',f'Rango permitido {minimo:g} a {maximo:g} {u_eca}.')
        m=re.fullmatch(r'\s*([<>≤≥]=?)?\s*(.+?)\s*',criterio)
        op,limtxt=m.groups()
        lim=numero(limtxt);op=op or ('≥' if fila['Tipo de criterio']=='Mínimo' else '≤')
        # Una lectura censurada (<L o >L) solo permite concluir si todo el intervalo queda de un lado del límite.
        mr=re.fullmatch(r'\s*([<>≤≥]=?)\s*(.+?)\s*',v)
        if mr:
            signo,umbral=mr.groups();b=numero(umbral)
            if signo in ('<','≤') and op in ('<','≤') and b<=lim:return 'CUMPLE',f'Resultado {v} está por debajo del máximo {lim:g}.'
            if signo in ('>','≥') and op in ('>','≥') and b>=lim:return 'CUMPLE',f'Resultado {v} está por encima del mínimo {lim:g}.'
            if signo in ('>','≥') and op in ('<','≤') and b>=lim:return 'NO CUMPLE',f'Resultado {v} supera el máximo {lim:g}.'
            if signo in ('<','≤') and op in ('>','≥') and b<=lim:return 'NO CUMPLE',f'Resultado {v} queda por debajo del mínimo {lim:g}.'
            return 'NO EVALUABLE',f'El intervalo implícito en {v} cruza el límite {criterio}.'
        if lim==0 and r in ('ausencia','ausente','nodetectado'):
            return 'CUMPLE',f'Ausencia reportada; criterio {op}{lim:g} {u_eca}.'
        if lim==0 and r in ('presencia','presente','detectado'):
            return 'NO CUMPLE',f'Presencia reportada; criterio {op}{lim:g} {u_eca}.'
        actual=numero(v)
        ok={'≤':actual<=lim,'<':actual<lim,'≥':actual>=lim,'>':actual>lim}.get(op)
        if ok is None:return 'NO EVALUABLE',f'Operador no reconocido: {op}.'
        return ('CUMPLE' if ok else 'NO CUMPLE',f'Resultado {actual:g}; criterio {op}{lim:g} {u_eca}.')
    except (ValueError,TypeError,AttributeError):
        return 'NO EVALUABLE',f'Confirma el formato del resultado y del criterio: {criterio}.'


