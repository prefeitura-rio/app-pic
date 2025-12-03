# Lovable Dashboard - Replication Plan

## 1. Visual Comparison Overview

### Current State vs Lovable
Based on the screenshots provided:

**Our Current Dashboard:**
- Simple filter bar at top
- Basic metric cards in grid layout
- Missing most visualizations
- Different color scheme
- Less visual hierarchy

**Lovable Dashboard:**
- Two-level filter structure (Main + Regional)
- Rich metric cards with icons and color coding
- Multiple chart types (Line, Bar, Pie)
- Comprehensive dimension analysis
- Clear visual sections with proper spacing

---

## 2. Filter Architecture Differences

### Lovable Filter Structure (Two Levels)

#### Level 1: Main Filters
```typescript
// src/lovable_front/src/components/OverviewTab.tsx:37-96
<div className="bg-muted/30 rounded-lg p-4 space-y-3">
  <p className="text-sm font-medium">Filtros Principais</p>

  1. Grupo (Multi-select)
     - Options: Gestante, Criança
     - State: grupoFiltro

  2. Safra (Multi-select)
     - Options: All cohorts
     - State: safraFiltro

  3. Secretaria (Multi-select)
     - Options: Saúde, Educação, Assistência Social
     - State: secretariaFiltro
</div>
```

#### Level 2: Regional Filters
```typescript
// src/lovable_front/src/components/OverviewTab.tsx:98-155
<div className="bg-muted/30 rounded-lg p-4 space-y-3">
  <p className="text-sm font-medium">Filtros Regionais</p>

  1. Bairro (Multi-select with search)
     - Searchable dropdown
     - State: bairroFiltro

  2. CAP (Multi-select)
     - Coordenadoria de Área Programática
     - State: capFiltro

  3. CRE (Multi-select)
     - Coordenadoria Regional de Educação
     - State: creFiltro

  4. CAS (Multi-select)
     - Centro de Assistência Social
     - State: casFiltro
</div>
```

### Our Current Filter Structure
```typescript
// Single-level filters in CommonFilters
- bairro
- cre
- cras (not CAS)
- escola
- clinica
- safra (cohort)
- grupo
- status
- situacao
```

### Changes Needed

**Frontend (DashboardClient.tsx + OverviewTab.tsx):**
1. Split filters into two visual sections (Main + Regional)
2. Add CAP filter (coordinate area)
3. Rename CRAS → CAS for consistency
4. Add Secretaria filter (dimension-based: Saúde, Educação, Assistência)
5. Make bairro searchable with ComboBox component

**Backend (dashboard.py):**
1. Add CAP column mapping
2. Handle Secretaria filter (filter by dimension columns)
3. Update filter options config for new fields

---

## 3. Main Metrics Cards

### Lovable Main Metrics (3 Cards)

```typescript
// src/lovable_front/src/components/OverviewTab.tsx:171-185
<div className="grid gap-4 md:grid-cols-3">

  1. Total de Participantes
     - Value: stats.subset.length
     - Icon: Users
     - Variant: "default"
     - Color: Blue/Default

  2. % Regular
     - Value: stats.completudeGeral + "%"
     - Icon: Activity (checkmark pulse)
     - Variant: "success"
     - Color: Green
     - Description: "Cumprindo todos os protocolos"

  3. % Irregular
     - Value: stats.emAlertaGeral + "%"
     - Icon: AlertTriangle
     - Variant: "destructive"
     - Color: Red
     - Description: "Com protocolos violados"
</div>
```

### Calculation Logic Needed

```typescript
// From lovable_front/src/hooks/useDashboardData.ts (inferred)
completudeGeral = (participantes_regulares / total_participantes) * 100
emAlertaGeral = (participantes_irregulares / total_participantes) * 100

// Regular = participant with 0 violated protocols
// Irregular = participant with >= 1 violated protocols
```

### Our Current Main Metrics
- total_participantes_geral (✓ exists)
- total_participantes_ativos/inativos (✓ exists)
- total_participantes_em_atencao (different concept)

### Changes Needed

**Backend (schemas.py):**
```python
class Dashboard(BaseModel):
    # ... existing fields ...

    # NEW FIELDS
    total_participantes_regulares: int
    total_participantes_irregulares: int
    percentual_regular: float
    percentual_irregular: float
```

**Backend (dashboard.py - _calculate_dashboard_metrics):**
```python
# Calculate regulares/irregulares
df_regulares = df.filter(pl.col("total_protocolos_violados") == 0)
df_irregulares = df.filter(pl.col("total_protocolos_violados") > 0)

total_regulares = len(df_regulares)
total_irregulares = len(df_irregulares)
perc_regular = (total_regulares / total_geral * 100) if total_geral > 0 else 0.0
perc_irregular = (total_irregulares / total_geral * 100) if total_geral > 0 else 0.0
```

**Frontend (OverviewTab.tsx):**
```typescript
import { StatCard } from "@/app/components/StatCard";
import { Users, Activity, AlertTriangle } from "lucide-react";

<div className="grid gap-4 md:grid-cols-3">
  <StatCard
    title="Total de Participantes"
    value={data.total_participantes_geral}
    icon={Users}
    variant="default"
  />
  <StatCard
    title="% Regular"
    value={`${data.percentual_regular.toFixed(1)}%`}
    description="Cumprindo todos os protocolos"
    icon={Activity}
    variant="success"
  />
  <StatCard
    title="% Irregular"
    value={`${data.percentual_irregular.toFixed(1)}%`}
    description="Com protocolos violados"
    icon={AlertTriangle}
    variant="destructive"
  />
</div>
```

**Frontend (Create StatCard.tsx):**
```typescript
// Copy from lovable_front/src/components/StatCard.tsx
// Already has proper variant styles and icon support
```

---

## 4. Dimensão Assistência Social (3 Indicators)

### Lovable Implementation

```typescript
// src/lovable_front/src/components/OverviewTab.tsx:188-246
<div className="space-y-3">
  <h3 className="text-lg font-semibold flex items-center gap-2">
    Dimensão Assistência Social
  </h3>

  <div className="grid gap-3 md:grid-cols-3">

    1. Bolsa Família
       - Metric: % participants receiving Bolsa Família
       - Icon: 💰
       - Calculation: (with_bolsa_familia / total) * 100
       - Color: bg-muted

    2. CadÚnico Atualizado
       - Metric: % participants with updated CadÚnico
       - Icon: 📋
       - Calculation: (cadunico_atualizado / total) * 100
       - Color: bg-muted

    3. Equipe de Referência
       - Metric: % participants with reference team
       - Icon: 👥
       - Calculation: (com_equipe_referencia / total) * 100
       - Color: bg-muted
  </div>
</div>
```

### Data Needed
Check if these columns exist in `endpoint_participante`:
- `assistencia_bolsa_familia` (boolean or status)
- `assistencia_cadunico_atualizado` (boolean or date check)
- `assistencia_equipe_referencia` (boolean or status)

### Backend Changes

**schemas.py:**
```python
class Dashboard(BaseModel):
    # ... existing fields ...

    # ASSISTÊNCIA SOCIAL
    assistencia_bolsa_familia_total: int
    assistencia_bolsa_familia_percentual: float
    assistencia_cadunico_atualizado_total: int
    assistencia_cadunico_atualizado_percentual: float
    assistencia_equipe_referencia_total: int
    assistencia_equipe_referencia_percentual: float
```

**dashboard.py:**
```python
# Assistência Social indicators
bolsa_familia_total = (
    df.filter(pl.col("assistencia_bolsa_familia") == True).height
    if "assistencia_bolsa_familia" in df.columns
    else 0
)
bolsa_familia_perc = (bolsa_familia_total / total_geral * 100) if total_geral > 0 else 0.0

cadunico_total = (
    df.filter(pl.col("assistencia_cadunico_atualizado") == True).height
    if "assistencia_cadunico_atualizado" in df.columns
    else 0
)
cadunico_perc = (cadunico_total / total_geral * 100) if total_geral > 0 else 0.0

equipe_ref_total = (
    df.filter(pl.col("assistencia_equipe_referencia") == True).height
    if "assistencia_equipe_referencia" in df.columns
    else 0
)
equipe_ref_perc = (equipe_ref_total / total_geral * 100) if total_geral > 0 else 0.0
```

### Frontend (OverviewTab.tsx)

```typescript
<div className="space-y-3">
  <h3 className="text-lg font-semibold flex items-center gap-2">
    Dimensão Assistência Social
  </h3>

  <div className="grid gap-3 md:grid-cols-3">
    <div className="bg-muted rounded-lg p-4">
      <p className="text-sm font-medium">💰 Bolsa Família</p>
      <p className="text-2xl font-bold">
        {data.assistencia_bolsa_familia_percentual.toFixed(1)}%
      </p>
      <p className="text-xs text-muted-foreground">
        {data.assistencia_bolsa_familia_total} participantes
      </p>
    </div>

    <div className="bg-muted rounded-lg p-4">
      <p className="text-sm font-medium">📋 CadÚnico Atualizado</p>
      <p className="text-2xl font-bold">
        {data.assistencia_cadunico_atualizado_percentual.toFixed(1)}%
      </p>
      <p className="text-xs text-muted-foreground">
        {data.assistencia_cadunico_atualizado_total} participantes
      </p>
    </div>

    <div className="bg-muted rounded-lg p-4">
      <p className="text-sm font-medium">👥 Equipe de Referência</p>
      <p className="text-2xl font-bold">
        {data.assistencia_equipe_referencia_percentual.toFixed(1)}%
      </p>
      <p className="text-xs text-muted-foreground">
        {data.assistencia_equipe_referencia_total} participantes
      </p>
    </div>
  </div>
</div>
```

---

## 5. Dimensão Educação (2 Indicators)

### Lovable Implementation

```typescript
// Similar structure to Assistência Social
<div className="grid gap-3 md:grid-cols-2">

  1. Frequência Escolar
     - Metric: % participants with adequate school attendance
     - Icon: 📚
     - Calculation: (frequencia_adequada / total) * 100

  2. Matrícula em Creche
     - Metric: % children enrolled in daycare
     - Icon: 🏫
     - Calculation: (matriculados_creche / total_criancas) * 100
</div>
```

### Data Needed
- `educacao_frequencia_adequada` (boolean or percentage check)
- `educacao_matricula_creche` (boolean)
- Filter by `grupo == 'criança'` for creche metric

### Backend Changes

**schemas.py:**
```python
class Dashboard(BaseModel):
    # ... existing fields ...

    # EDUCAÇÃO
    educacao_frequencia_adequada_total: int
    educacao_frequencia_adequada_percentual: float
    educacao_matricula_creche_total: int
    educacao_matricula_creche_percentual: float
```

**dashboard.py:**
```python
# Educação indicators
freq_adequada_total = (
    df.filter(pl.col("educacao_frequencia_adequada") == True).height
    if "educacao_frequencia_adequada" in df.columns
    else 0
)
freq_adequada_perc = (freq_adequada_total / total_geral * 100) if total_geral > 0 else 0.0

# Matrícula creche - apenas crianças
df_criancas = df.filter(pl.col("grupo") == "criança") if "grupo" in df.columns else df
total_criancas = len(df_criancas)
matricula_creche_total = (
    df_criancas.filter(pl.col("educacao_matricula_creche") == True).height
    if "educacao_matricula_creche" in df.columns
    else 0
)
matricula_creche_perc = (
    (matricula_creche_total / total_criancas * 100) if total_criancas > 0 else 0.0
)
```

---

## 6. Dimensão Saúde (3 Indicators)

### Lovable Implementation

```typescript
<div className="grid gap-3 md:grid-cols-3">

  1. Consultas Infantis
     - Metric: % children with regular pediatric appointments
     - Icon: 👶
     - Calculation: (consultas_em_dia / total_criancas) * 100

  2. Pré-natal
     - Metric: % pregnant women with adequate prenatal care
     - Icon: 🤰
     - Calculation: (pre_natal_adequado / total_gestantes) * 100

  3. Vacinação em Dia
     - Metric: % participants with vaccination up to date
     - Icon: 💉
     - Calculation: (vacinacao_em_dia / total) * 100
</div>
```

### Data Needed
- `saude_consultas_infantis_em_dia` (boolean)
- `saude_pre_natal_adequado` (boolean)
- `saude_vacinacao_em_dia` (boolean)

### Backend Changes

**schemas.py:**
```python
class Dashboard(BaseModel):
    # ... existing fields ...

    # SAÚDE
    saude_consultas_infantis_total: int
    saude_consultas_infantis_percentual: float
    saude_pre_natal_total: int
    saude_pre_natal_percentual: float
    saude_vacinacao_total: int
    saude_vacinacao_percentual: float
```

**dashboard.py:**
```python
# Consultas infantis - apenas crianças
consultas_infantis_total = (
    df_criancas.filter(pl.col("saude_consultas_infantis_em_dia") == True).height
    if "saude_consultas_infantis_em_dia" in df.columns
    else 0
)
consultas_infantis_perc = (
    (consultas_infantis_total / total_criancas * 100) if total_criancas > 0 else 0.0
)

# Pré-natal - apenas gestantes
df_gestantes = df.filter(pl.col("grupo") == "gestante") if "grupo" in df.columns else df
total_gestantes = len(df_gestantes)
pre_natal_total = (
    df_gestantes.filter(pl.col("saude_pre_natal_adequado") == True).height
    if "saude_pre_natal_adequado" in df.columns
    else 0
)
pre_natal_perc = (pre_natal_total / total_gestantes * 100) if total_gestantes > 0 else 0.0

# Vacinação - todos
vacinacao_total = (
    df.filter(pl.col("saude_vacinacao_em_dia") == True).height
    if "saude_vacinacao_em_dia" in df.columns
    else 0
)
vacinacao_perc = (vacinacao_total / total_geral * 100) if total_geral > 0 else 0.0
```

---

## 7. Resultado do Programa (Line Chart)

### Lovable Implementation

```typescript
// src/lovable_front/src/components/OverviewTab.tsx:326-397
<Card>
  <CardHeader>
    <CardTitle>Resultado do Programa</CardTitle>
    <CardDescription>Evolução temporal da completude</CardDescription>
  </CardHeader>
  <CardContent>
    <LineChart data={stats.resultadoPrograma} height={300}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="mes" />
      <YAxis domain={[0, 100]} />
      <Tooltip />
      <Legend />

      <Line type="monotone" dataKey="todos" stroke="#8b5cf6" name="Todos" />
      <Line type="monotone" dataKey="saude" stroke="#ef4444" name="Saúde" />
      <Line type="monotone" dataKey="educacao" stroke="#f59e0b" name="Educação" />
      <Line type="monotone" dataKey="assistencia" stroke="#10b981" name="Assistência" />
    </LineChart>
  </CardContent>
</Card>
```

### Data Structure Needed

```typescript
interface ResultadoProgramaPoint {
  mes: string;          // "2024-01", "2024-02", etc.
  todos: number;        // % completude geral
  saude: number;        // % completude saúde
  educacao: number;     // % completude educação
  assistencia: number;  // % completude assistência
}

resultadoPrograma: ResultadoProgramaPoint[]
```

### Backend Changes

**schemas.py:**
```python
class ResultadoProgramaPoint(BaseModel):
    mes: str
    todos: float
    saude: float
    educacao: float
    assistencia: float

class Dashboard(BaseModel):
    # ... existing fields ...
    resultado_programa: list[ResultadoProgramaPoint]
```

**dashboard.py:**
```python
# Resultado do Programa (monthly evolution)
# This requires historical data or monthly snapshots
# If not available, can calculate current month only

def _calculate_resultado_programa(df: pl.DataFrame) -> list[ResultadoProgramaPoint]:
    """
    Calculate monthly evolution of program results.

    NOTE: This requires either:
    1. Historical snapshot data per month
    2. Last update date per participant to reconstruct history
    3. Or just return current month snapshot
    """

    # Option 1: If we have cohort data, group by cohort as months
    if "cohort" in df.columns:
        monthly_data = []
        cohorts = df["cohort"].unique().sort()

        for cohort in cohorts:
            df_month = df.filter(pl.col("cohort") == cohort)
            total = len(df_month)

            if total == 0:
                continue

            # Completude geral
            regulares = df_month.filter(pl.col("total_protocolos_violados") == 0).height
            completude_todos = (regulares / total * 100) if total > 0 else 0.0

            # Completude por dimensão (all protocols in dimension OK)
            saude_ok = df_month.filter(pl.col("saude_protocolos_violados") == 0).height
            completude_saude = (saude_ok / total * 100) if total > 0 else 0.0

            educacao_ok = df_month.filter(pl.col("educacao_protocolos_violados") == 0).height
            completude_educacao = (educacao_ok / total * 100) if total > 0 else 0.0

            assistencia_ok = df_month.filter(
                pl.col("assistencia_protocolos_violados") == 0
            ).height
            completude_assistencia = (assistencia_ok / total * 100) if total > 0 else 0.0

            monthly_data.append(
                ResultadoProgramaPoint(
                    mes=str(cohort),
                    todos=completude_todos,
                    saude=completude_saude,
                    educacao=completude_educacao,
                    assistencia=completude_assistencia,
                )
            )

        return monthly_data

    # Option 2: Return single point for current data
    total = len(df)
    regulares = df.filter(pl.col("total_protocolos_violados") == 0).height
    completude_todos = (regulares / total * 100) if total > 0 else 0.0

    # ... calculate dimension completudes ...

    return [
        ResultadoProgramaPoint(
            mes="Atual",
            todos=completude_todos,
            saude=completude_saude,
            educacao=completude_educacao,
            assistencia=completude_assistencia,
        )
    ]
```

### Frontend (OverviewTab.tsx)

```typescript
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/app/components/ui/card";

<Card>
  <CardHeader>
    <CardTitle>Resultado do Programa</CardTitle>
    <CardDescription>Evolução temporal da completude por dimensão</CardDescription>
  </CardHeader>
  <CardContent>
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data.resultado_programa}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="mes" />
        <YAxis domain={[0, 100]} />
        <Tooltip formatter={(value) => `${value.toFixed(1)}%`} />
        <Legend />

        <Line
          type="monotone"
          dataKey="todos"
          stroke="#8b5cf6"
          strokeWidth={2}
          name="Todos"
        />
        <Line
          type="monotone"
          dataKey="saude"
          stroke="#ef4444"
          strokeWidth={2}
          name="Saúde"
        />
        <Line
          type="monotone"
          dataKey="educacao"
          stroke="#f59e0b"
          strokeWidth={2}
          name="Educação"
        />
        <Line
          type="monotone"
          dataKey="assistencia"
          stroke="#10b981"
          strokeWidth={2}
          name="Assistência"
        />
      </LineChart>
    </ResponsiveContainer>
  </CardContent>
</Card>
```

---

## 8. Other Visualizations from Lovable

### 8.1. Análise Tempo de Irregularidade

```typescript
// Multiple cards showing time-based metrics
1. Tempo Médio de Irregularidade
   - Average days participants stay irregular

2. Participantes com Alta Permanência
   - Count of participants irregular > 90 days

3. Distribuição por Faixa de Tempo
   - Bar chart: 0-30 days, 31-60, 61-90, 90+ days
```

**Data Needed:**
- `data_primeira_irregularidade` (date)
- `data_ultima_regularizacao` (date)
- Calculate: `dias_irregular = today - data_primeira_irregularidade`

### 8.2. Participantes por Safra

```typescript
// Stacked bar chart
<BarChart data={stats.participantesPorSafra}>
  <Bar dataKey="ativos" stackId="a" fill="#10b981" name="Ativos" />
  <Bar dataKey="inativos" stackId="a" fill="#6b7280" name="Inativos" />
</BarChart>
```

**Data Needed:**
- Group by `cohort`
- Count `status == "ativo"` vs `status != "ativo"`

### 8.3. Motivos de Saída

```typescript
// Pie chart
<PieChart>
  <Pie data={stats.motivosSaida} dataKey="value" nameKey="name">
    {stats.motivosSaida.map((entry, index) => (
      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
    ))}
  </Pie>
</PieChart>
```

**Data Needed:**
- Filter `status != "ativo"`
- Group by `status_inativo_motivo`
- Count occurrences

**NOTE:** This already exists in current Dashboard! (`distribuicao_motivo_saida`)

---

## 9. Color Scheme and Styling

### Lovable Color Palette

```typescript
// Primary colors
Primary (Purple): #8b5cf6
Success (Green): #10b981
Warning (Orange): #f59e0b
Destructive (Red): #ef4444
Muted: #6b7280

// Background
bg-muted: Light gray background for cards
bg-muted/30: Semi-transparent muted background

// Borders
rounded-lg: 8px border radius
border-border: Default border color
```

### Card Spacing
```typescript
// Grid gaps
gap-3: 12px between cards
gap-4: 16px between sections

// Padding
p-4: 16px padding inside cards

// Section spacing
space-y-3: 12px vertical spacing
space-y-6: 24px vertical spacing between major sections
```

### Typography
```typescript
// Headers
text-lg font-semibold: Section titles
text-2xl font-bold: Main metric values

// Body
text-sm font-medium: Card labels
text-xs text-muted-foreground: Descriptions
```

---

## 10. Implementation Phases

### Phase 1: Backend Data Preparation (Priority: High)

**File: `src/api/v1/schemas.py`**
- [ ] Add `total_participantes_regulares` field
- [ ] Add `total_participantes_irregulares` field
- [ ] Add `percentual_regular` field
- [ ] Add `percentual_irregular` field
- [ ] Add 6 Assistência Social fields (total + percentual × 3)
- [ ] Add 4 Educação fields (total + percentual × 2)
- [ ] Add 6 Saúde fields (total + percentual × 3)
- [ ] Add `ResultadoProgramaPoint` schema
- [ ] Add `resultado_programa: list[ResultadoProgramaPoint]` field

**File: `src/api/v1/dashboard.py`**
- [ ] Implement regulares/irregulares calculation
- [ ] Implement Assistência Social metrics (verify column names)
- [ ] Implement Educação metrics (verify column names)
- [ ] Implement Saúde metrics (verify column names)
- [ ] Implement `_calculate_resultado_programa()` function
- [ ] Add CAP filter support
- [ ] Add Secretaria filter support (filter by dimension)

**Estimated Time:** 4-6 hours

### Phase 2: Frontend Filter Restructure (Priority: High)

**Files:**
- `src/frontend/app/components/OverviewTab.tsx`
- `src/frontend/app/types.ts`

**Tasks:**
- [ ] Split filters into two sections (Main + Regional)
- [ ] Create Main Filters section (Grupo, Safra, Secretaria)
- [ ] Create Regional Filters section (Bairro, CAP, CRE, CAS)
- [ ] Make Bairro searchable with ComboBox
- [ ] Update filter types and API calls

**Estimated Time:** 2-3 hours

### Phase 3: Frontend Main Metrics (Priority: High)

**Files:**
- Create `src/frontend/app/components/StatCard.tsx`
- Update `src/frontend/app/components/OverviewTab.tsx`

**Tasks:**
- [ ] Copy StatCard component from Lovable
- [ ] Implement 3 main metric cards (Total, % Regular, % Irregular)
- [ ] Add proper icons and variant styling
- [ ] Test responsiveness

**Estimated Time:** 1-2 hours

### Phase 4: Frontend Dimension Cards (Priority: Medium)

**File: `src/frontend/app/components/OverviewTab.tsx`**

**Tasks:**
- [ ] Create Dimensão Assistência Social section
- [ ] Implement 3 indicator cards (Bolsa Família, CadÚnico, Equipe Ref.)
- [ ] Create Dimensão Educação section
- [ ] Implement 2 indicator cards (Frequência, Matrícula Creche)
- [ ] Create Dimensão Saúde section
- [ ] Implement 3 indicator cards (Consultas, Pré-natal, Vacinação)
- [ ] Add emojis and proper formatting

**Estimated Time:** 2-3 hours

### Phase 5: Frontend Charts (Priority: Medium)

**File: `src/frontend/app/components/OverviewTab.tsx`**

**Tasks:**
- [ ] Install/verify Recharts dependency
- [ ] Implement "Resultado do Programa" line chart
- [ ] Implement "Participantes por Safra" stacked bar chart
- [ ] Verify "Motivos de Saída" pie chart (already exists?)
- [ ] Add Card wrappers with proper titles

**Estimated Time:** 3-4 hours

### Phase 6: Advanced Analytics (Priority: Low)

**Tasks:**
- [ ] Research data availability for irregularity time tracking
- [ ] Implement "Tempo de Irregularidade" metrics if data exists
- [ ] Add time distribution charts

**Estimated Time:** 4-6 hours (depends on data availability)

### Phase 7: Polish and Testing (Priority: High)

**Tasks:**
- [ ] Adjust spacing to match Lovable exactly
- [ ] Verify color scheme consistency
- [ ] Test all filters (cascading + independent states)
- [ ] Test responsiveness on mobile/tablet
- [ ] Performance testing with real data
- [ ] Cross-browser testing

**Estimated Time:** 2-3 hours

---

## 11. Data Verification Checklist

Before implementing, verify these columns exist in `endpoint_participante`:

**For Assistência Social:**
- [ ] `assistencia_bolsa_familia` or similar
- [ ] `assistencia_cadunico_atualizado` or similar
- [ ] `assistencia_equipe_referencia` or similar

**For Educação:**
- [ ] `educacao_frequencia_adequada` or similar
- [ ] `educacao_matricula_creche` or similar

**For Saúde:**
- [ ] `saude_consultas_infantis_em_dia` or similar
- [ ] `saude_pre_natal_adequado` or similar
- [ ] `saude_vacinacao_em_dia` or similar

**For Time Tracking:**
- [ ] `data_primeira_irregularidade` or similar
- [ ] Historical snapshot data or cohort grouping

**For Regional Filters:**
- [ ] `cap` (Coordenadoria de Área Programática)
- [ ] Verify CAS vs CRAS naming

**Action:** Run query to inspect column names first:
```sql
SELECT column_name
FROM `{PROJECT_ID}.{DATASET_ID}.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'endpoint_participante'
ORDER BY column_name
```

---

## 12. Risk Assessment

### High Risk Items
1. **Missing columns** - Dimension indicators might not exist in BigQuery table
   - Mitigation: Verify all columns before implementation
   - Fallback: Mock data or hide unavailable metrics

2. **Historical data** - Resultado do Programa requires time series
   - Mitigation: Check if cohort can be used as proxy for months
   - Fallback: Show single point for current state

3. **Performance** - Calculating all metrics might be slow
   - Mitigation: Already using Polars (fast)
   - Fallback: Consider caching individual metrics

### Medium Risk Items
1. **Filter complexity** - Secretaria filter affects multiple columns
   - Mitigation: Filter by dimension columns (saude_, educacao_, assistencia_)

2. **Cascading logic** - Already complex, adding more filters
   - Mitigation: Current cascading logic already works well

### Low Risk Items
1. **Frontend styling** - Mostly CSS changes
2. **Chart libraries** - Recharts already used in Lovable
3. **Icons** - lucide-react already available

---

## 13. Success Criteria

The implementation will be considered complete when:

1. ✅ **Filters match Lovable exactly:**
   - Two-level structure (Main + Regional)
   - All filter options available
   - Cascading works correctly
   - Independent between tabs

2. ✅ **Main metrics display correctly:**
   - Total Participantes
   - % Regular (green)
   - % Irregular (red)

3. ✅ **All dimension cards display:**
   - 3 Assistência Social indicators
   - 2 Educação indicators
   - 3 Saúde indicators

4. ✅ **Charts render correctly:**
   - Resultado do Programa (line chart)
   - Participantes por Safra (stacked bar)
   - Motivos de Saída (pie chart)

5. ✅ **Visual match:**
   - Color scheme matches Lovable
   - Spacing matches Lovable
   - Typography matches Lovable
   - Responsive on all screen sizes

6. ✅ **Performance:**
   - Dashboard loads < 2s (cache hit)
   - Filters apply < 1s
   - No regressions in existing functionality

---

## 14. Questions for User

Before starting implementation, please confirm:

1. **Column names:** Should I first query BigQuery to verify all dimension indicator columns exist?

2. **Historical data:** Do we have monthly snapshots or should we use cohort as a proxy for time series?

3. **Priority:** Should I implement in the phased order above, or is there a specific section you want first?

4. **Missing data:** If some dimension indicators don't exist in BigQuery, should I:
   - Hide those cards?
   - Show with "Data not available" message?
   - Create mock/placeholder data?

5. **CAP/CAS:** Can you confirm the correct column names for:
   - CAP (Coordenadoria de Área Programática)
   - CAS vs CRAS naming

---

## 15. Next Steps

Once you approve this plan:

1. I'll query BigQuery to verify all column names
2. Update schemas.py with new fields
3. Implement backend calculations in dashboard.py
4. Update frontend filters structure
5. Implement main metrics cards
6. Implement dimension cards
7. Implement charts
8. Polish styling to match Lovable exactly

**Estimated Total Time:** 18-27 hours of implementation work

Ready to proceed? Please confirm the plan and answer the questions in Section 14.
