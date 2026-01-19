"use client";

import { useState, useEffect } from "react";
import { UserAccessRecord, AvailableIds, CreateUserRequest, UpdateUserRequest, IdWithName } from "@/app/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, Loader2 } from "lucide-react";
import { VirtualizedIdMultiSelect } from "@/app/components/admin/VirtualizedIdMultiSelect";

interface UserFormProps {
  availableIds: AvailableIds;
  currentUser: UserAccessRecord; // Current logged-in user
  user?: UserAccessRecord; // If provided, edit mode
  onSubmit: (data: CreateUserRequest | UpdateUserRequest) => void;
  onCancel: () => void;
  isLoading: boolean;
  error?: string;
}

export function UserForm({
  availableIds,
  currentUser,
  user,
  onSubmit,
  onCancel,
  isLoading,
  error,
}: UserFormProps) {
  const isEditMode = !!user;
  const canEditSuperAdmin = currentUser.is_super_admin;

  // Form state
  const [cpf, setCpf] = useState("");
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const [ocupacao, setOcupacao] = useState("");
  const [secretaria, setSecretaria] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [isSuperAdmin, setIsSuperAdmin] = useState(false);
  const [notes, setNotes] = useState("");

  const [selectedCras, setSelectedCras] = useState<IdWithName[]>([]);
  const [selectedEscolas, setSelectedEscolas] = useState<IdWithName[]>([]);
  const [selectedCres, setSelectedCres] = useState<IdWithName[]>([]);
  const [selectedAps, setSelectedAps] = useState<IdWithName[]>([]);
  const [selectedCas, setSelectedCas] = useState<IdWithName[]>([]);
  const [selectedClinicas, setSelectedClinicas] = useState<IdWithName[]>([]);

  // Initialize form with user data if editing
  useEffect(() => {
    if (user) {
      setCpf(user.cpf);
      setEmail(user.email || "");
      setNome(user.nome || "");
      setOcupacao(user.ocupacao || "");
      setSecretaria(user.secretaria || "");
      setIsAdmin(user.is_admin);
      setIsSuperAdmin(user.is_super_admin);
      setNotes(user.notes || "");

      setSelectedCras(user.id_cras_list || []);
      setSelectedEscolas(user.id_escola_list || []);
      setSelectedCres(user.id_cre_list || []);
      setSelectedAps(user.id_ap_list || []);
      setSelectedCas(user.id_cas_list || []);
      setSelectedClinicas(user.id_clinica_familia_list || []);
    } else {
      // Reset form
      setCpf("");
      setEmail("");
      setNome("");
      setOcupacao("");
      setSecretaria("");
      setIsAdmin(false);
      setIsSuperAdmin(false);
      setNotes("");
      setSelectedCras([]);
      setSelectedEscolas([]);
      setSelectedCres([]);
      setSelectedAps([]);
      setSelectedCas([]);
      setSelectedClinicas([]);
    }
  }, [user]);

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
      // Update mode
      const updateData: UpdateUserRequest = {
        email: email || null,
        nome: nome || null,
        ocupacao: ocupacao || null,
        secretaria: secretaria || null,
        is_admin: isAdmin,
        is_super_admin: isSuperAdmin,
        id_cras_list: selectedCras.length > 0 ? selectedCras : null,
        id_escola_list: selectedEscolas.length > 0 ? selectedEscolas : null,
        id_cre_list: selectedCres.length > 0 ? selectedCres : null,
        id_ap_list: selectedAps.length > 0 ? selectedAps : null,
        id_cas_list: selectedCas.length > 0 ? selectedCas : null,
        id_clinica_familia_list: selectedClinicas.length > 0 ? selectedClinicas : null,
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
        id_cras_list: selectedCras.length > 0 ? selectedCras : null,
        id_escola_list: selectedEscolas.length > 0 ? selectedEscolas : null,
        id_cre_list: selectedCres.length > 0 ? selectedCres : null,
        id_ap_list: selectedAps.length > 0 ? selectedAps : null,
        id_cas_list: selectedCas.length > 0 ? selectedCas : null,
        id_clinica_familia_list: selectedClinicas.length > 0 ? selectedClinicas : null,
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

          <div className="grid gap-4 md:grid-cols-2">
            {/* ASSISTÊNCIA SOCIAL */}
            {/* CAS */}
            <VirtualizedIdMultiSelect
              label="CAS (Centros de Assistência Social)"
              options={availableIds.cas}
              selected={selectedCas}
              onChange={setSelectedCas}
              disabled={isLoading}
              tooltip="Coordenadorias de Assistência Social - selecione para dar acesso a todos os CRAS da região"
            />

            {/* CRAS */}
            <VirtualizedIdMultiSelect
              label="CRAS"
              options={availableIds.cras}
              selected={selectedCras}
              onChange={setSelectedCras}
              disabled={isLoading}
              tooltip="Centros de Referência de Assistência Social que o usuário poderá acessar"
            />

            {/* EDUCAÇÃO */}
            {/* CRE (Coordenadoria Regional de Educação) */}
            <VirtualizedIdMultiSelect
              label="CRE (Coordenadoria Regional de Educação)"
              options={availableIds.cres}
              selected={selectedCres}
              onChange={setSelectedCres}
              disabled={isLoading}
              tooltip="Coordenadorias Regionais de Educação - selecione para dar acesso a todas as escolas da região"
            />

            {/* Escolas */}
            <VirtualizedIdMultiSelect
              label="Escolas"
              options={availableIds.escolas}
              selected={selectedEscolas}
              onChange={setSelectedEscolas}
              disabled={isLoading}
              tooltip="Unidades escolares que o usuário poderá visualizar no sistema"
            />

            {/* SAÚDE */}
            {/* AP (Área Programática) */}
            <VirtualizedIdMultiSelect
              label="AP ( Área Programática)"
              options={availableIds.aps}
              selected={selectedAps}
              onChange={setSelectedAps}
              disabled={isLoading}
              tooltip="Coordenadorias de Área Programática de Saúde - divisão territorial do município"
            />

            {/* Clínicas da Família */}
            <VirtualizedIdMultiSelect
              label="Clínicas da Família"
              options={availableIds.clinicas}
              selected={selectedClinicas}
              onChange={setSelectedClinicas}
              disabled={isLoading}
              tooltip="Clínicas da Família e unidades de saúde que o usuário poderá acessar"
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
