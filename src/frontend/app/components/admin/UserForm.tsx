"use client";

import { useState, useMemo } from "react";
import { UserAccessRecord, CreateUserRequest, UpdateUserRequest, IdWithName } from "@/app/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, Loader2 } from "lucide-react";
import { VirtualizedIdMultiSelect } from "@/app/components/admin/VirtualizedIdMultiSelect";
import { SecretariasAcessoField } from "@/app/components/admin/SecretariasAcessoField";
import { useUnitOptions } from "@/app/components/admin/useUnitOptions";

interface UserFormProps {
  currentUser: UserAccessRecord; // Current logged-in user
  user?: UserAccessRecord; // If provided, edit mode
  onSubmit: (data: CreateUserRequest | UpdateUserRequest) => void;
  onCancel: () => void;
  isLoading: boolean;
  error?: string;
}

export function UserForm({
  currentUser,
  user,
  onSubmit,
  onCancel,
  isLoading,
  error,
}: UserFormProps) {
  const isEditMode = !!user;

  const casOptions = useUnitOptions("cas");
  const crasOptions = useUnitOptions("cras");
  const cresOptions = useUnitOptions("cres");
  const escolasOptions = useUnitOptions("escolas");
  const apsOptions = useUnitOptions("aps");
  const clinicasOptions = useUnitOptions("clinicas");
  const equipesOptions = useUnitOptions("equipes_familia");

  // Secretarias que o admin logado pode atribuir (subset da própria secretarias_acesso)
  const allowedSecretariasAcesso = useMemo(() => {
    if (currentUser?.is_super_admin) {
      return ["SME", "SMS", "SMAS"];
    }
    if (currentUser?.is_admin) {
      return currentUser?.secretarias_acesso || [];
    }
    return [];
  }, [currentUser]);

  // Form state
  // NOTA: inicializado direto a partir de `user` (sem useEffect) porque este
  // componente sempre remonta ao trocar de aba (Radix TabsContent desmonta
  // conteúdo inativo), então `user` já está correto no momento do mount.
  const [cpf, setCpf] = useState(user?.cpf ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [nome, setNome] = useState(user?.nome ?? "");
  const [ocupacao, setOcupacao] = useState(user?.ocupacao ?? "");
  const [secretaria, setSecretaria] = useState(user?.secretaria ?? "");
  const [isAdmin, setIsAdmin] = useState(user?.is_admin ?? false);
  // Não há UI para promover/rebaixar super admin neste formulário; apenas preserva o valor existente.
  const isSuperAdmin = user?.is_super_admin ?? false;
  const [notes, setNotes] = useState(user?.notes ?? "");

  const [selectedCras, setSelectedCras] = useState<IdWithName[]>(user?.id_cras_list ?? []);
  const [selectedEscolas, setSelectedEscolas] = useState<IdWithName[]>(user?.id_escola_list ?? []);
  const [selectedCres, setSelectedCres] = useState<IdWithName[]>(user?.id_cre_list ?? []);
  const [selectedAps, setSelectedAps] = useState<IdWithName[]>(user?.id_ap_list ?? []);
  const [selectedCas, setSelectedCas] = useState<IdWithName[]>(user?.id_cas_list ?? []);
  const [selectedClinicas, setSelectedClinicas] = useState<IdWithName[]>(user?.id_clinica_familia_list ?? []);
  const [selectedEquipesFamilia, setSelectedEquipesFamilia] = useState<IdWithName[]>(user?.id_equipe_familia_list ?? []);
  const [secretariasAcesso, setSecretariasAcesso] = useState<string[]>(user?.secretarias_acesso ?? []);

  // Handle CPF input (only numbers)
  const handleCpfChange = (value: string) => {
    const numbers = value.replace(/\D/g, "");
    if (numbers.length <= 11) {
      setCpf(numbers);
    }
  };

  // Format CPF for display
  const formatCpf = (value: string) => {
    return value.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  };

  // Handle submit
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (isEditMode) {
      // Update mode.
      //
      // IMPORTANTE: listas de equipamentos são SEMPRE enviadas (mesmo
      // vazias). O backend trata `null` como "não fornecido → não mexer
      // nos grants deste tipo" (`_replace_policy_grants`), então enviar
      // null ao limpar um tipo deixaria as permissões antigas intactas;
      // uma lista vazia é o que efetivamente remove os grants.
      const updateData: UpdateUserRequest = {
        email: email || null,
        nome: nome || null,
        ocupacao: ocupacao || null,
        secretaria: secretaria || null,
        is_admin: isAdmin,
        is_super_admin: isSuperAdmin,
        id_cras_list: selectedCras,
        id_escola_list: selectedEscolas,
        id_cre_list: selectedCres,
        id_ap_list: selectedAps,
        id_cas_list: selectedCas,
        id_clinica_familia_list: selectedClinicas,
        id_equipe_familia_list: selectedEquipesFamilia,
        secretarias_acesso: secretariasAcesso,
        notes: notes || null,
      };
      onSubmit(updateData);
    } else {
      // Create mode
      const createData: CreateUserRequest = {
        cpf,
        email: email || null,
        nome: nome || null,
        ocupacao: ocupacao || null,
        secretaria: secretaria || null,
        is_admin: isAdmin,
        is_super_admin: isSuperAdmin,
        id_cras_list: selectedCras,
        id_escola_list: selectedEscolas,
        id_cre_list: selectedCres,
        id_ap_list: selectedAps,
        id_cas_list: selectedCas,
        id_clinica_familia_list: selectedClinicas,
        id_equipe_familia_list: selectedEquipesFamilia,
        secretarias_acesso: secretariasAcesso,
        notes: notes || null,
      };
      onSubmit(createData);
    }
  };

  // Validation
  const isValid = isEditMode || (cpf.length === 11);

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-2xl font-bold">
          {isEditMode ? "Editar Usuário" : "Novo Usuário"}
        </h2>
        <p className="text-muted-foreground mt-1">
          {isEditMode
            ? "Atualize as permissões e informações do usuário"
            : "Adicione um novo usuário ao sistema com permissões específicas"}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Error message */}
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Informações do Usuário */}
        <div className="space-y-4 rounded-lg border p-4">
          <h3 className="text-sm font-medium mb-4">Informações do Usuário</h3>

          {/* CPF */}
          <div className="space-y-2">
            <Label htmlFor="cpf" title="Cadastro de Pessoa Física - documento obrigatório">CPF *</Label>
            <Input
              id="cpf"
              placeholder="00000000000"
              value={cpf.length === 11 ? formatCpf(cpf) : cpf}
              onChange={(e) => handleCpfChange(e.target.value)}
              disabled={isEditMode || isLoading}
              required
              title={isEditMode ? "O CPF não pode ser alterado após criação" : "Digite os 11 dígitos do CPF sem pontos ou traços"}
            />
            <p className="text-xs text-muted-foreground">
              {isEditMode
                ? "O CPF não pode ser alterado"
                : "Digite apenas números (11 dígitos)"}
            </p>
          </div>

          {/* Nome */}
          <div className="space-y-2">
            <Label htmlFor="nome" title="Nome completo do usuário conforme documento">Nome Completo</Label>
            <Input
              id="nome"
              placeholder="Ex: Maria da Silva Santos"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              disabled={isLoading}
              title="Digite o nome completo do usuário"
            />
          </div>

          {/* Email */}
          <div className="space-y-2">
            <Label htmlFor="email" title="Email institucional do usuário">Email</Label>
            <Input
              id="email"
              type="email"
              placeholder="Ex: usuario@rio.rj.gov.br"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isLoading}
              title="Digite o email institucional do usuário"
            />
          </div>

          {/* Ocupação e Secretaria */}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ocupacao" title="Cargo ou função do usuário">Ocupação</Label>
              <Input
                id="ocupacao"
                placeholder="Ex: Coordenador, Assistente Social"
                value={ocupacao}
                onChange={(e) => setOcupacao(e.target.value)}
                disabled={isLoading}
                title="Cargo ou função exercida pelo usuário"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="secretaria" title="Secretaria municipal onde o usuário trabalha">Secretaria</Label>
              <Input
                id="secretaria"
                placeholder="Ex: SMAS, SME, SMS"
                value={secretaria}
                onChange={(e) => setSecretaria(e.target.value)}
                disabled={isLoading}
                title="Secretaria municipal (SMAS, SME, SMS, etc.)"
              />
            </div>
          </div>
        </div>

        {/* Admin Permissions */}
        <div className="space-y-4 rounded-lg border p-4">
          <h3 className="text-sm font-medium mb-4" title="Defina o nível de acesso administrativo do usuário">Permissões de Administração</h3>

          {/* Is Admin Checkbox */}
          <div className="flex items-start gap-3" title="Administradores podem criar e editar outros usuários com permissões iguais ou menores">
            <Checkbox
              id="is_admin"
              checked={isAdmin}
              onCheckedChange={(checked) => setIsAdmin(checked as boolean)}
              disabled={isLoading || isSuperAdmin}
              className="mt-1"
            />
            <div className="flex-1 space-y-1">
              <Label
                htmlFor="is_admin"
                className="text-sm font-medium leading-none cursor-pointer"
                title="Marque para conceder permissões de administrador"
              >
                Admin
              </Label>
              <p className="text-sm text-muted-foreground">
                Pode gerenciar outros usuários (apenas com subset de seus IDs)
              </p>
            </div>
          </div>

        </div>

        {/* ID Selections */}
        <div className="space-y-4">
          <div className="space-y-2">
            <h3 className="text-sm font-medium" title="Defina quais unidades o usuário pode visualizar no sistema">Permissões de Acesso</h3>
            <p className="text-xs text-muted-foreground">
              Selecione os IDs aos quais o usuário terá acesso. Deixe vazio para sem restrições nesse tipo.
            </p>
          </div>

          {/* Acesso a Protocolos - PRIMEIRO CAMPO */}
          <div className="space-y-2">
            <Label title="Controla quais protocolos o usuário pode visualizar">
              Acesso a Protocolos
            </Label>
            <SecretariasAcessoField
              value={secretariasAcesso}
              onChange={setSecretariasAcesso}
              allowedValues={allowedSecretariasAcesso}
              disabled={isLoading || (!currentUser?.is_admin && !currentUser?.is_super_admin)}
            />
            <p className="text-xs text-muted-foreground">
              {currentUser?.is_super_admin
                ? "Controla quais protocolos o usuário pode visualizar e filtrar"
                : currentUser?.is_admin
                ? "Você pode atribuir acesso a protocolos específicos de cada secretaria"
                : "Somente administradores podem alterar o acesso a protocolos"}
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {/* ASSISTÊNCIA SOCIAL */}
            {/* CAS */}
            <VirtualizedIdMultiSelect
              label="CAS (Centros de Assistência Social)"
              options={casOptions.options}
              selected={selectedCas}
              onChange={setSelectedCas}
              disabled={isLoading}
              onOpen={casOptions.onOpen}
              loading={casOptions.isLoading}
              tooltip="Coordenadorias de Assistência Social - selecione para dar acesso a todos os CRAS da região"
            />

            {/* CRAS */}
            <VirtualizedIdMultiSelect
              label="CRAS"
              options={crasOptions.options}
              selected={selectedCras}
              onChange={setSelectedCras}
              disabled={isLoading}
              onOpen={crasOptions.onOpen}
              loading={crasOptions.isLoading}
              tooltip="Centros de Referência de Assistência Social que o usuário poderá acessar"
            />

            {/* EDUCAÇÃO */}
            {/* CRE (Coordenadoria Regional de Educação) */}
            <VirtualizedIdMultiSelect
              label="CRE (Coordenadoria Regional de Educação)"
              options={cresOptions.options}
              selected={selectedCres}
              onChange={setSelectedCres}
              disabled={isLoading}
              onOpen={cresOptions.onOpen}
              loading={cresOptions.isLoading}
              tooltip="Coordenadorias Regionais de Educação - selecione para dar acesso a todas as escolas da região"
            />

            {/* Escolas */}
            <VirtualizedIdMultiSelect
              label="Escolas"
              options={escolasOptions.options}
              selected={selectedEscolas}
              onChange={setSelectedEscolas}
              disabled={isLoading}
              onOpen={escolasOptions.onOpen}
              loading={escolasOptions.isLoading}
              tooltip="Unidades escolares que o usuário poderá visualizar no sistema"
            />

            {/* SAÚDE */}
            {/* CAP (Coordenadoria de Área Programática) */}
            <VirtualizedIdMultiSelect
              label="CAP (Coordenadoria de Área Programática)"
              options={apsOptions.options}
              selected={selectedAps}
              onChange={setSelectedAps}
              disabled={isLoading}
              onOpen={apsOptions.onOpen}
              loading={apsOptions.isLoading}
              tooltip="Coordenadorias de Área Programática de Saúde - divisão territorial do município"
            />

            {/* Clínicas da Família */}
            <VirtualizedIdMultiSelect
              label="Clínicas da Família"
              options={clinicasOptions.options}
              selected={selectedClinicas}
              onChange={setSelectedClinicas}
              disabled={isLoading}
              onOpen={clinicasOptions.onOpen}
              loading={clinicasOptions.isLoading}
              tooltip="Clínicas da Família e unidades de saúde que o usuário poderá acessar"
            />

            {/* Equipes de Saúde da Família */}
            <VirtualizedIdMultiSelect
              label="Equipes de Saúde da Família"
              options={equipesOptions.options}
              selected={selectedEquipesFamilia}
              onChange={setSelectedEquipesFamilia}
              disabled={isLoading}
              onOpen={equipesOptions.onOpen}
              loading={equipesOptions.isLoading}
              tooltip="Equipes de Saúde da Família (ESF) que o usuário poderá acessar"
            />
          </div>
        </div>

        {/* Notes */}
        <div className="space-y-2">
          <Label htmlFor="notes" title="Campo livre para observações internas sobre o usuário">Notas (opcional)</Label>
          <Textarea
            id="notes"
            placeholder="Adicione observações sobre este usuário..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={isLoading}
            rows={3}
            title="Observações internas visíveis apenas para administradores"
          />
        </div>

        {/* Action buttons */}
        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={isLoading}
            title="Cancelar e voltar para a lista de usuários"
          >
            Cancelar
          </Button>
          <Button
            type="submit"
            disabled={!isValid || isLoading}
            title={isEditMode ? "Salvar alterações do usuário" : "Criar novo usuário com as permissões definidas"}
          >
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isEditMode ? "Atualizar" : "Criar Usuário"}
          </Button>
        </div>
      </form>
    </div>
  );
}
