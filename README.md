# Finanzas — Dashboard personal de gastos

## Que hace

Aplicacion web local (Streamlit) para gestionar las finanzas personales. Permite importar cartolas bancarias, visualizar gastos por categoria, registrar deudas y analizar el presupuesto con ayuda de IA (Groq/Llama).

## Flujo paso a paso

1. El usuario abre el dashboard con `streamlit run dashboard.py`
2. En la pantalla principal ve un resumen del mes: ingresos, gastos, balance
3. Puede importar cartolas en formato CSV o Excel desde la pagina "Importar Cartola"
4. El sistema categoriza automaticamente las transacciones usando reglas configurables
5. Se pueden agregar gastos manuales (efectivo, transferencias sin cartola)
6. La pagina "Deudas & Pendientes" muestra compromisos de pago futuros
7. El "Analisis & Presupuesto" usa Groq/Llama para dar recomendaciones basadas en el historial
8. Los datos se sincronizan con Google Sheets para acceso desde el celular

## Como ejecutar

```bash
cd "3. Automatizaciones/Finanzas"
streamlit run dashboard.py
# Abre automaticamente en http://localhost:8501
```

## Paginas disponibles

| Pagina | Funcion |
|--------|---------|
| Dashboard | Resumen del mes: ingresos, gastos, balance |
| Transacciones | Lista completa con filtros y busqueda |
| Gastos Manuales | Agregar gastos en efectivo o sin cartola |
| Deudas & Pendientes | Compromisos futuros (cuotas, pagos recurrentes) |
| Historico | Evolucion de gastos mes a mes |
| Analisis & Presupuesto | Recomendaciones con IA (Groq/Llama) |
| Importar Cartola | Carga de archivos CSV/Excel del banco |
| Categorias & Reglas | Configurar como se clasifican las transacciones |

## Credenciales requeridas (en `1. Config/.env`)

| Variable | Descripcion |
|----------|-------------|
| `GROQ_API_KEY` | Para el modulo de analisis con IA |
| Google Service Account | `service_account.json` en la carpeta del proyecto |

## Archivos clave

| Archivo/Carpeta | Funcion |
|----------------|---------|
| `dashboard.py` | Punto de entrada, configura Streamlit y rutas de navegacion |
| `utils/` | Cargadores de datos, conexion a Sheets, CSS global |
| `views/` | Una vista por pagina del dashboard |
| `finance_local.db` | Base de datos SQLite local con todas las transacciones |
| `abrir_dashboard.bat` | Atajo para abrir el dashboard con doble clic |
