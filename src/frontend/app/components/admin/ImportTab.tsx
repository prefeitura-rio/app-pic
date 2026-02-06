"use client";

import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import Papa from "papaparse";
import ExcelJS from "exceljs";

import { apiService } from "@/app/services/api";
import {
  IdWithName,
  AvailableIds,
  ImportedUser,
  ImportedUserWithEdits,
  BatchImportResult,
  UserAccessRecord,
} from "@/app/types";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { VirtualizedIdMultiSelect } from "./VirtualizedIdMultiSelect";
import {
  Download,
  Upload,
  Search,
  Filter,
  Check,
  X,
  AlertCircle,
  CheckCircle2,
  Clock,
  Undo2,
  FileSpreadsheet,
  Lock,
} from "lucide-react";
import { cn } from "@/app/utils/utils";

// Status colors for badges
const STATUS_COLORS = {
  new: "bg-green-100 text-green-800 border-green-200",
  exists: "bg-amber-100 text-amber-800 border-amber-200", // Amber = will update existing
  error: "bg-red-100 text-red-800 border-red-200",
  done: "bg-gray-100 text-gray-600 border-gray-200",
};

// Row background colors (only for non-selectable statuses)
const STATUS_ROW_COLORS = {
  error: "bg-red-50",
  done: "bg-gray-50",
};

const STATUS_LABELS = {
  new: "Novo",
  exists: "Atualizar", // Indicates it will update existing user
  error: "Erro",
  done: "Feito",
};

const STATUS_ICONS = {
  new: <CheckCircle2 className="h-3 w-3" />,
  exists: <Clock className="h-3 w-3" />,
  error: <AlertCircle className="h-3 w-3" />,
  done: <Check className="h-3 w-3" />,
};

interface ImportTabProps {
  availableIds: AvailableIds;
  currentUser: UserAccessRecord;
  onPermissionsApplied?: () => void; // Callback para atualizar tabela de usuários
  prePopulatedUsers?: UserAccessRecord[]; // Usuários pré-selecionados da tabela de usuários
}

type UserStatus = "new" | "exists" | "error" | "done";
type StatusFilter = "all" | UserStatus | "selectable" | "blocked";
type SortBy = "nome" | "cpf" | "status";
type SortOrder = "asc" | "desc";

export function ImportTab({ availableIds, currentUser, onPermissionsApplied, prePopulatedUsers }: ImportTabProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Upload state
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  // Imported users state (with local edits)
  const [importedUsers, setImportedUsers] = useState<ImportedUserWithEdits[]>([]);
  const [importResult, setImportResult] = useState<BatchImportResult | null>(null);

  // Selection state
  const [selectedCpfs, setSelectedCpfs] = useState<Set<string>>(new Set());

  // Filter state
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortBy>("nome");
  const [sortOrder, setSortOrder] = useState<SortOrder>("asc");

  // Permissions state
  const [isAdmin, setIsAdmin] = useState(false);
  const [selectedCras, setSelectedCras] = useState<IdWithName[]>([]);
  const [selectedEscolas, setSelectedEscolas] = useState<IdWithName[]>([]);
  const [selectedCres, setSelectedCres] = useState<IdWithName[]>([]);
  const [selectedAps, setSelectedAps] = useState<IdWithName[]>([]);
  const [selectedCas, setSelectedCas] = useState<IdWithName[]>([]);
  const [selectedClinicas, setSelectedClinicas] = useState<IdWithName[]>([]);

  // Undo state
  const [lastBatchCpfs, setLastBatchCpfs] = useState<string[]>([]);

  // Populate importedUsers when prePopulatedUsers is provided
  useEffect(() => {
    if (prePopulatedUsers && prePopulatedUsers.length > 0) {
      // Deduplicar por CPF (manter primeiro)
      const seen = new Set<string>();
      const dedupedUsers = prePopulatedUsers.filter((u) => {
        if (seen.has(u.cpf)) return false;
        seen.add(u.cpf);
        return true;
      });
      const usersWithStatus: ImportedUserWithEdits[] = dedupedUsers.map((user) => ({
        cpf: user.cpf,
        nome: user.nome,
        email: user.email,
        ocupacao: user.ocupacao,
        secretaria: user.secretaria,
        status: "exists" as const,
        is_admin: user.is_admin,
        is_super_admin: user.is_super_admin,
        id_cras_list: user.id_cras_list,
        id_escola_list: user.id_escola_list,
        id_cre_list: user.id_cre_list,
        id_ap_list: user.id_ap_list,
        id_cas_list: user.id_cas_list,
        id_clinica_familia_list: user.id_clinica_familia_list,
      }));
      setImportedUsers(usersWithStatus);
      // Select all pre-populated users
      setSelectedCpfs(new Set(dedupedUsers.map((u) => u.cpf)));
    }
  }, [prePopulatedUsers]);

  // Filter available IDs based on current user permissions
  // Super admin sees all, segmented admin only sees their own IDs
  const filteredAvailableIds = useMemo(() => {
    if (currentUser.is_super_admin) {
      return availableIds;
    }

    // Segmented admin: only show IDs they can assign (their own IDs)
    return {
      cras: currentUser.id_cras_list || [],
      escolas: currentUser.id_escola_list || [],
      cres: currentUser.id_cre_list || [],
      aps: currentUser.id_ap_list || [],
      cas: currentUser.id_cas_list || [],
      clinicas: currentUser.id_clinica_familia_list || [],
    };
  }, [availableIds, currentUser]);

  // Editing state
  const [editingCell, setEditingCell] = useState<{
    cpf: string;
    field: "nome" | "ocupacao" | "secretaria";
  } | null>(null);

  // Mutations
  const importMutation = useMutation({
    mutationFn: (file: File) => apiService.batchImportUsers(file),
    onSuccess: (result) => {
      setImportResult(result);
      // Deduplicar por CPF (manter primeiro)
      const seen = new Set<string>();
      const dedupedUsers = result.imported_users.filter((u) => {
        if (seen.has(u.cpf)) return false;
        seen.add(u.cpf);
        return true;
      });
      setImportedUsers(
        dedupedUsers.map((u) => ({
          ...u,
          status: u.status as UserStatus,
        }))
      );
      setSelectedCpfs(new Set());
      const dupCount = result.imported_users.length - dedupedUsers.length;
      toast.success("Importacao concluida", {
        description: `${result.imported} importados, ${result.skipped} pulados, ${result.errors.length} erros${dupCount > 0 ? `, ${dupCount} duplicados removidos` : ""}`,
      });
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (error: Error) => {
      toast.error("Erro na importacao", { description: error.message });
    },
  });

  const permissionsMutation = useMutation({
    mutationFn: apiService.batchUpdatePermissions,
    onSuccess: (result) => {
      // Mark updated users as "done"
      const updatedCpfs = new Set(
        selectedCpfs
      );
      setImportedUsers((prev) =>
        prev.map((u) =>
          updatedCpfs.has(u.cpf) ? { ...u, status: "done" as UserStatus } : u
        )
      );
      setLastBatchCpfs(Array.from(selectedCpfs));
      setSelectedCpfs(new Set());

      toast.success("Permissoes atribuidas", {
        description: `${result.updated} usuarios atualizados`,
      });
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });

      // Atualizar tabela de usuários com bypass de cache
      onPermissionsApplied?.();
    },
    onError: (error: Error) => {
      toast.error("Erro ao atribuir permissoes", { description: error.message });
    },
  });

  const undoMutation = useMutation({
    mutationFn: apiService.undoBatchPermissions,
    onSuccess: (result) => {
      // Mark undone users as "new" again
      const undoneCpfs = new Set(lastBatchCpfs);
      setImportedUsers((prev) =>
        prev.map((u) =>
          undoneCpfs.has(u.cpf) ? { ...u, status: "new" as UserStatus } : u
        )
      );
      setLastBatchCpfs([]);

      toast.success("Acao desfeita", {
        description: `${result.updated} usuarios revertidos`,
      });
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (error: Error) => {
      toast.error("Erro ao desfazer", { description: error.message });
    },
  });

  // Filter and sort users
  const filteredUsers = useMemo(() => {
    let users = [...importedUsers];

    // Se não for super admin, esconder super admins da lista
    if (!currentUser.is_super_admin) {
      users = users.filter((u) => !u.is_super_admin);
    }

    // Filter by search
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      users = users.filter(
        (u) =>
          u.cpf.includes(term) ||
          (u.nome || "").toLowerCase().includes(term) ||
          (u.edited?.nome || "").toLowerCase().includes(term)
      );
    }

    // Filter by status
    if (statusFilter !== "all") {
      if (statusFilter === "selectable") {
        // Mostrar apenas usuários que podem ser editados
        users = users.filter((u) => {
          if (u.status !== "new" && u.status !== "exists") return false;
          if (u.status === "new") return true;
          const targetIsAdmin = u.is_admin === true;
          const targetIsSuperAdmin = u.is_super_admin === true;
          if (currentUser.is_super_admin) {
            return !targetIsSuperAdmin;
          }
          return !targetIsAdmin && !targetIsSuperAdmin;
        });
      } else if (statusFilter === "blocked") {
        // Mostrar apenas usuários bloqueados (existem mas não podem ser editados)
        users = users.filter((u) => {
          if (u.status !== "exists") return false;
          const targetIsAdmin = u.is_admin === true;
          const targetIsSuperAdmin = u.is_super_admin === true;
          if (currentUser.is_super_admin) {
            return targetIsSuperAdmin;
          }
          return targetIsAdmin || targetIsSuperAdmin;
        });
      } else {
        users = users.filter((u) => u.status === statusFilter);
      }
    }

    // Sort
    users.sort((a, b) => {
      let valueA: string;
      let valueB: string;

      switch (sortBy) {
        case "nome":
          valueA = (a.edited?.nome || a.nome || "").toLowerCase();
          valueB = (b.edited?.nome || b.nome || "").toLowerCase();
          break;
        case "cpf":
          valueA = a.cpf;
          valueB = b.cpf;
          break;
        case "status":
          valueA = a.status;
          valueB = b.status;
          break;
        default:
          valueA = "";
          valueB = "";
      }

      if (sortOrder === "asc") {
        return valueA.localeCompare(valueB);
      } else {
        return valueB.localeCompare(valueA);
      }
    });

    return users;
  }, [importedUsers, searchTerm, statusFilter, sortBy, sortOrder, currentUser.is_super_admin]);

  // Count selectable users (new = insert, exists = update)
  // Aplica regras de permissão:
  // - Admin: pode editar apenas users (não admins nem super_admins)
  // - Super Admin: pode editar users e admins (não outros super_admins)
  const selectableUsers = useMemo(
    () => filteredUsers.filter((u) => {
      // Só pode selecionar status "new" ou "exists"
      if (u.status !== "new" && u.status !== "exists") return false;

      // Novos usuários sempre podem ser selecionados
      if (u.status === "new") return true;

      // Para usuários existentes, aplicar regras de permissão
      const targetIsAdmin = u.is_admin === true;
      const targetIsSuperAdmin = u.is_super_admin === true;

      if (currentUser.is_super_admin) {
        // Super admin pode editar users e admins, não outros super_admins
        return !targetIsSuperAdmin;
      } else {
        // Admin pode editar apenas users (não admins nem super_admins)
        return !targetIsAdmin && !targetIsSuperAdmin;
      }
    }),
    [filteredUsers, currentUser.is_super_admin]
  );

  // Handle file selection
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  // Handle file drop
  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      const ext = droppedFile.name.toLowerCase();
      if (ext.endsWith(".csv") || ext.endsWith(".xlsx")) {
        setFile(droppedFile);
      } else {
        toast.error("Formato invalido", {
          description: "Use arquivos CSV ou XLSX",
        });
      }
    }
  };

  // Handle import
  const handleImport = () => {
    if (file) {
      setIsUploading(true);
      importMutation.mutate(file, {
        onSettled: () => setIsUploading(false),
      });
    }
  };

  // Handle select all visible
  const handleSelectAllVisible = () => {
    const newSelection = new Set(selectedCpfs);
    selectableUsers.forEach((u) => newSelection.add(u.cpf));
    setSelectedCpfs(newSelection);
  };

  // Handle deselect all
  const handleDeselectAll = () => {
    setSelectedCpfs(new Set());
  };

  // Handle toggle selection
  const handleToggleSelect = (cpf: string) => {
    const newSelection = new Set(selectedCpfs);
    if (newSelection.has(cpf)) {
      newSelection.delete(cpf);
    } else {
      newSelection.add(cpf);

      // Se for o primeiro usuário "exists" selecionado, preencher permissões existentes
      const user = importedUsers.find((u) => u.cpf === cpf);
      if (user?.status === "exists" && newSelection.size === 1) {
        // Preencher com permissões existentes do usuário
        if (user.is_admin !== undefined && user.is_admin !== null) {
          setIsAdmin(user.is_admin);
        }
        if (user.id_cras_list) setSelectedCras(user.id_cras_list);
        if (user.id_escola_list) setSelectedEscolas(user.id_escola_list);
        if (user.id_cre_list) setSelectedCres(user.id_cre_list);
        if (user.id_ap_list) setSelectedAps(user.id_ap_list);
        if (user.id_cas_list) setSelectedCas(user.id_cas_list);
        if (user.id_clinica_familia_list) setSelectedClinicas(user.id_clinica_familia_list);
      }
    }
    setSelectedCpfs(newSelection);
  };

  // Handle apply permissions
  const handleApplyPermissions = () => {
    if (selectedCpfs.size === 0) return;

    const users = importedUsers
      .filter((u) => selectedCpfs.has(u.cpf))
      .map((u) => ({
        cpf: u.cpf,
        nome: u.edited?.nome || u.nome || null,
        email: u.email || null,
        ocupacao: u.edited?.ocupacao || u.ocupacao || null,
        secretaria: u.edited?.secretaria || u.secretaria || null,
      }));

    permissionsMutation.mutate({
      users,
      is_admin: isAdmin,
      id_cras_list: selectedCras.length > 0 ? selectedCras : null,
      id_escola_list: selectedEscolas.length > 0 ? selectedEscolas : null,
      id_cre_list: selectedCres.length > 0 ? selectedCres : null,
      id_ap_list: selectedAps.length > 0 ? selectedAps : null,
      id_cas_list: selectedCas.length > 0 ? selectedCas : null,
      id_clinica_familia_list: selectedClinicas.length > 0 ? selectedClinicas : null,
    });
  };

  // Handle undo
  const handleUndo = () => {
    if (lastBatchCpfs.length === 0) return;
    undoMutation.mutate({ cpfs: lastBatchCpfs });
  };

  // Handle inline edit
  const handleEditField = (
    cpf: string,
    field: "nome" | "ocupacao" | "secretaria",
    value: string
  ) => {
    setImportedUsers((prev) =>
      prev.map((u) =>
        u.cpf === cpf
          ? {
              ...u,
              edited: {
                ...u.edited,
                [field]: value,
              },
            }
          : u
      )
    );
  };

  // Download template
  const handleDownloadTemplate = async (format: "csv" | "xlsx") => {
    const headers = ["cpf", "nome", "email", "ocupacao", "secretaria"];
    const sampleData = [
      ["12345678901", "Joao Silva", "joao@email.com", "Coordenador", "SMAS"],
      ["98765432100", "Maria Santos", "maria@email.com", "Assistente Social", "SMAS"],
    ];

    if (format === "csv") {
      const csv = Papa.unparse({
        fields: headers,
        data: sampleData,
      });
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "template_usuarios.csv";
      a.click();
      URL.revokeObjectURL(url);
    } else {
      const workbook = new ExcelJS.Workbook();
      const worksheet = workbook.addWorksheet("Usuarios");
      worksheet.addRow(headers);
      sampleData.forEach((row) => worksheet.addRow(row));

      const buffer = await workbook.xlsx.writeBuffer();
      const blob = new Blob([buffer], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "template_usuarios.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  // Build preview text
  const previewText = useMemo(() => {
    const parts: string[] = [];

    if (selectedCras.length > 0) {
      parts.push(`${selectedCras.length} CRAS`);
    }
    if (selectedEscolas.length > 0) {
      parts.push(`${selectedEscolas.length} Escolas`);
    }
    if (selectedCres.length > 0) {
      parts.push(`${selectedCres.length} CREs`);
    }
    if (selectedAps.length > 0) {
      parts.push(`${selectedAps.length} CAPs`);
    }
    if (selectedCas.length > 0) {
      parts.push(`${selectedCas.length} CAS`);
    }
    if (selectedClinicas.length > 0) {
      parts.push(`${selectedClinicas.length} Clinicas`);
    }

    if (parts.length === 0) {
      return `Atribuir para ${selectedCpfs.size} usuarios (sem IDs selecionados)`;
    }

    return `Atribuir ${parts.join(", ")} para ${selectedCpfs.size} usuarios`;
  }, [
    selectedCpfs.size,
    selectedCras,
    selectedEscolas,
    selectedCres,
    selectedAps,
    selectedCas,
    selectedClinicas,
  ]);

  // Format CPF for display
  const formatCpf = (cpf: string) => {
    if (!cpf || cpf.length !== 11) return cpf;
    return `${cpf.slice(0, 3)}.${cpf.slice(3, 6)}.${cpf.slice(6, 9)}-${cpf.slice(9)}`;
  };

  return (
    <div className="space-y-6">
      {/* Download Templates */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5" />
            Templates de Importacao
          </CardTitle>
        </CardHeader>
        <CardContent className="flex gap-3">
          <Button
            variant="outline"
            onClick={() => handleDownloadTemplate("csv")}
          >
            <Download className="h-4 w-4 mr-2" />
            Download Template CSV
          </Button>
          <Button
            variant="outline"
            onClick={() => handleDownloadTemplate("xlsx")}
          >
            <Download className="h-4 w-4 mr-2" />
            Download Template XLSX
          </Button>
        </CardContent>
      </Card>

      {/* Upload Area */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Upload de Arquivo
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div
            className={cn(
              "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
              "hover:border-primary hover:bg-primary/5",
              file ? "border-primary bg-primary/5" : "border-muted-foreground/25"
            )}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx"
              onChange={handleFileSelect}
              className="hidden"
            />
            {file ? (
              <div className="space-y-2">
                <FileSpreadsheet className="h-12 w-12 mx-auto text-primary" />
                <p className="font-medium">{file.name}</p>
                <p className="text-sm text-muted-foreground">
                  {(file.size / 1024).toFixed(1)} KB
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <Upload className="h-12 w-12 mx-auto text-muted-foreground" />
                <p className="font-medium">Arraste o arquivo aqui ou clique para selecionar</p>
                <p className="text-sm text-muted-foreground">
                  Formatos aceitos: CSV, XLSX (max 1000 linhas)
                </p>
              </div>
            )}
          </div>

          {file && (
            <div className="mt-4 flex gap-3">
              <Button onClick={handleImport} disabled={isUploading || importMutation.isPending}>
                {isUploading || importMutation.isPending ? "Importando..." : "Importar"}
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setFile(null);
                  if (fileInputRef.current) fileInputRef.current.value = "";
                }}
              >
                Cancelar
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Import Result Summary */}
      {importResult && (
        <Card>
          <CardContent className="pt-6">
            <div className="flex flex-wrap gap-4">
              <Badge variant="outline" className="text-base py-2 px-4 bg-green-50 text-green-700 border-green-200">
                <CheckCircle2 className="h-4 w-4 mr-2" />
                {importResult.imported} importados
              </Badge>
              <Badge variant="outline" className="text-base py-2 px-4 bg-yellow-50 text-yellow-700 border-yellow-200">
                <Clock className="h-4 w-4 mr-2" />
                {importResult.skipped} ja existiam
              </Badge>
              {importResult.errors.length > 0 && (
                <Badge variant="outline" className="text-base py-2 px-4 bg-red-50 text-red-700 border-red-200">
                  <AlertCircle className="h-4 w-4 mr-2" />
                  {importResult.errors.length} erros
                </Badge>
              )}
            </div>

            {/* Error list */}
            {importResult.errors.length > 0 && (
              <div className="mt-4 p-4 bg-red-50 rounded-lg border border-red-200">
                <h4 className="font-medium text-red-800 mb-2">Erros encontrados:</h4>
                <ul className="space-y-1 text-sm text-red-700">
                  {importResult.errors.slice(0, 10).map((err, idx) => (
                    <li key={idx}>
                      Linha {err.row}: {err.cpf ? `CPF "${err.cpf}" - ` : ""}{err.error}
                    </li>
                  ))}
                  {importResult.errors.length > 10 && (
                    <li>... e mais {importResult.errors.length - 10} erros</li>
                  )}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Two-panel layout */}
      {importedUsers.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: '1.5rem' }}>
          {/* Left panel - Users (60%) */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Usuarios Importados</CardTitle>

              {/* Search and filters */}
              <div className="flex flex-col gap-3 mt-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Buscar por CPF ou nome..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                  />
                </div>

                <div className="flex gap-2 flex-wrap">
                  <Select
                    value={statusFilter}
                    onValueChange={(v) => setStatusFilter(v as StatusFilter)}
                  >
                    <SelectTrigger className="w-32">
                      <SelectValue placeholder="Status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Todos</SelectItem>
                      <SelectItem value="new">Novos</SelectItem>
                      <SelectItem value="exists">Existentes</SelectItem>
                      <SelectItem value="selectable">Editáveis</SelectItem>
                      <SelectItem value="blocked">Bloqueados</SelectItem>
                      <SelectItem value="done">Feitos</SelectItem>
                      <SelectItem value="error">Erros</SelectItem>
                    </SelectContent>
                  </Select>

                  <Select
                    value={sortBy}
                    onValueChange={(v) => setSortBy(v as SortBy)}
                  >
                    <SelectTrigger className="w-32">
                      <SelectValue placeholder="Ordenar" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="nome">Nome</SelectItem>
                      <SelectItem value="cpf">CPF</SelectItem>
                      <SelectItem value="status">Status</SelectItem>
                    </SelectContent>
                  </Select>

                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setSortOrder(sortOrder === "asc" ? "desc" : "asc")}
                    title={sortOrder === "asc" ? "Ordenar decrescente" : "Ordenar crescente"}
                  >
                    {sortOrder === "asc" ? "A-Z" : "Z-A"}
                  </Button>
                </div>
              </div>
            </CardHeader>

            <CardContent>
              {/* Selection controls */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Checkbox
                    checked={
                      selectableUsers.length > 0 &&
                      selectableUsers.every((u) => selectedCpfs.has(u.cpf))
                    }
                    onCheckedChange={(checked) => {
                      if (checked) {
                        handleSelectAllVisible();
                      } else {
                        handleDeselectAll();
                      }
                    }}
                    disabled={selectableUsers.length === 0}
                  />
                  <span className="text-sm text-muted-foreground">
                    {selectedCpfs.size} selecionados de {selectableUsers.length} disponiveis
                  </span>
                </div>
              </div>

              {/* User table */}
              <div className="border rounded-lg overflow-hidden max-h-[500px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-muted sticky top-0">
                    <tr>
                      <th className="p-2 w-8"></th>
                      <th className="p-2 w-10 text-center text-muted-foreground">#</th>
                      <th className="p-2 text-left">Status</th>
                      <th className="p-2 text-left">CPF</th>
                      <th className="p-2 text-left">Nome</th>
                      <th className="p-2 text-left">Email</th>
                      <th className="p-2 text-left">Tipo</th>
                      <th className="p-2 text-left">Ocupacao</th>
                      <th className="p-2 text-left">Secretaria</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map((user, index) => {
                      // Aplicar mesma lógica de selectableUsers para determinar se é selecionável
                      const isSelectable = (() => {
                        if (user.status !== "new" && user.status !== "exists") return false;
                        if (user.status === "new") return true;
                        // Para usuários existentes, aplicar regras de permissão
                        const targetIsAdmin = user.is_admin === true;
                        const targetIsSuperAdmin = user.is_super_admin === true;
                        if (currentUser.is_super_admin) {
                          return !targetIsSuperAdmin;
                        } else {
                          return !targetIsAdmin && !targetIsSuperAdmin;
                        }
                      })();
                      const isSelected = selectedCpfs.has(user.cpf);

                      // Determinar se é bloqueado (existe mas não pode editar por falta de permissão)
                      const isBlocked = user.status === "exists" && !isSelectable;

                      // Determinar tipo do usuário
                      const userType = user.is_super_admin ? "Super Admin" : user.is_admin ? "Admin" : "Usuário";

                      return (
                        <tr
                          key={`${user.cpf}-${index}`}
                          className={cn(
                            "border-t transition-colors",
                            isBlocked && "bg-red-50/50",
                            !isSelectable && !isBlocked && STATUS_ROW_COLORS[user.status as keyof typeof STATUS_ROW_COLORS],
                            isSelected && "bg-primary/10"
                          )}
                        >
                          {/* Checkbox */}
                          <td className="p-2">
                            <Checkbox
                              checked={isSelected}
                              onCheckedChange={() => handleToggleSelect(user.cpf)}
                              disabled={!isSelectable}
                              className={cn(
                                !isSelectable && "opacity-30",
                                isBlocked && "border-red-300"
                              )}
                            />
                          </td>

                          {/* Index */}
                          <td className="p-2 w-10 text-center text-xs text-muted-foreground/60">
                            {index + 1}
                          </td>

                          {/* Status */}
                          <td className="p-2">
                            {isBlocked ? (
                              <Badge
                                variant="outline"
                                className="text-xs bg-red-50 text-red-600 border-red-200"
                              >
                                <Lock className="h-3 w-3" />
                                <span className="ml-1">Bloqueado</span>
                              </Badge>
                            ) : (
                              <Badge
                                variant="outline"
                                className={cn("text-xs", STATUS_COLORS[user.status])}
                              >
                                {STATUS_ICONS[user.status]}
                                <span className="ml-1">{STATUS_LABELS[user.status]}</span>
                              </Badge>
                            )}
                          </td>

                          {/* CPF */}
                          <td className="p-2 font-mono text-xs">
                            {formatCpf(user.cpf)}
                          </td>

                          {/* Nome - Editable */}
                          <td className="p-2">
                            {editingCell?.cpf === user.cpf && editingCell?.field === "nome" ? (
                              <Input
                                autoFocus
                                defaultValue={user.edited?.nome || user.nome || ""}
                                className="h-7 text-sm"
                                onBlur={(e) => {
                                  handleEditField(user.cpf, "nome", e.target.value);
                                  setEditingCell(null);
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    handleEditField(user.cpf, "nome", e.currentTarget.value);
                                    setEditingCell(null);
                                  }
                                  if (e.key === "Escape") {
                                    setEditingCell(null);
                                  }
                                }}
                              />
                            ) : (
                              <span
                                className={cn(
                                  "cursor-pointer hover:bg-muted px-1 rounded",
                                  isSelectable && "hover:underline"
                                )}
                                onClick={() =>
                                  isSelectable &&
                                  setEditingCell({ cpf: user.cpf, field: "nome" })
                                }
                              >
                                {user.edited?.nome || user.nome || "-"}
                              </span>
                            )}
                          </td>

                          {/* Email - Display only */}
                          <td className="p-2 text-xs text-muted-foreground">
                            {user.email || "-"}
                          </td>

                          {/* Tipo */}
                          <td className="p-2">
                            {user.status === "new" ? (
                              <span className="text-xs text-muted-foreground">-</span>
                            ) : (
                              <Badge
                                variant={user.is_super_admin ? "destructive" : user.is_admin ? "default" : "secondary"}
                                className="text-xs"
                              >
                                {userType}
                              </Badge>
                            )}
                          </td>

                          {/* Ocupacao - Editable */}
                          <td className="p-2">
                            {editingCell?.cpf === user.cpf && editingCell?.field === "ocupacao" ? (
                              <Input
                                autoFocus
                                defaultValue={user.edited?.ocupacao || user.ocupacao || ""}
                                className="h-7 text-sm"
                                onBlur={(e) => {
                                  handleEditField(user.cpf, "ocupacao", e.target.value);
                                  setEditingCell(null);
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    handleEditField(user.cpf, "ocupacao", e.currentTarget.value);
                                    setEditingCell(null);
                                  }
                                  if (e.key === "Escape") {
                                    setEditingCell(null);
                                  }
                                }}
                              />
                            ) : (
                              <span
                                className={cn(
                                  "cursor-pointer hover:bg-muted px-1 rounded",
                                  isSelectable && "hover:underline"
                                )}
                                onClick={() =>
                                  isSelectable &&
                                  setEditingCell({ cpf: user.cpf, field: "ocupacao" })
                                }
                              >
                                {user.edited?.ocupacao || user.ocupacao || "-"}
                              </span>
                            )}
                          </td>

                          {/* Secretaria - Editable text */}
                          <td className="p-2">
                            {editingCell?.cpf === user.cpf && editingCell?.field === "secretaria" ? (
                              <Input
                                autoFocus
                                defaultValue={user.edited?.secretaria || user.secretaria || ""}
                                className="h-7 text-sm w-24"
                                onBlur={(e) => {
                                  handleEditField(user.cpf, "secretaria", e.target.value);
                                  setEditingCell(null);
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    handleEditField(user.cpf, "secretaria", e.currentTarget.value);
                                    setEditingCell(null);
                                  }
                                  if (e.key === "Escape") {
                                    setEditingCell(null);
                                  }
                                }}
                              />
                            ) : (
                              <span
                                className={cn(
                                  "cursor-pointer hover:bg-muted px-1 rounded",
                                  isSelectable && "hover:underline"
                                )}
                                onClick={() =>
                                  isSelectable &&
                                  setEditingCell({ cpf: user.cpf, field: "secretaria" })
                                }
                              >
                                {user.edited?.secretaria || user.secretaria || "-"}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Right panel - Permissions (40%) */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Permissoes</CardTitle>
            </CardHeader>

            <CardContent className="space-y-6">
              {/* Admin checkbox */}
              <div className="flex items-center gap-2">
                <Checkbox
                  id="is-admin"
                  checked={isAdmin}
                  onCheckedChange={(checked) => setIsAdmin(!!checked)}
                />
                <Label htmlFor="is-admin">Tornar admin</Label>
              </div>

              {/* ID selectors */}
              <VirtualizedIdMultiSelect
                label="CRAS"
                options={filteredAvailableIds.cras}
                selected={selectedCras}
                onChange={setSelectedCras}
                placeholder="Selecionar CRAS..."
              />

              <VirtualizedIdMultiSelect
                label="Escolas"
                options={filteredAvailableIds.escolas}
                selected={selectedEscolas}
                onChange={setSelectedEscolas}
                placeholder="Selecionar Escolas..."
              />

              <VirtualizedIdMultiSelect
                label="CRE"
                options={filteredAvailableIds.cres}
                selected={selectedCres}
                onChange={setSelectedCres}
                placeholder="Selecionar CREs..."
              />

              <VirtualizedIdMultiSelect
                label="CAP"
                options={filteredAvailableIds.aps}
                selected={selectedAps}
                onChange={setSelectedAps}
                placeholder="Selecionar CAPs..."
              />

              <VirtualizedIdMultiSelect
                label="CAS"
                options={filteredAvailableIds.cas}
                selected={selectedCas}
                onChange={setSelectedCas}
                placeholder="Selecionar CAS..."
              />

              <VirtualizedIdMultiSelect
                label="Clinicas"
                options={filteredAvailableIds.clinicas}
                selected={selectedClinicas}
                onChange={setSelectedClinicas}
                placeholder="Selecionar Clinicas..."
              />

              {/* Preview */}
              {selectedCpfs.size > 0 && (
                <div className="p-3 bg-muted rounded-lg text-sm">
                  {previewText}
                </div>
              )}

              {/* Action buttons */}
              <div className="flex flex-col gap-2">
                <Button
                  onClick={handleApplyPermissions}
                  disabled={selectedCpfs.size === 0 || permissionsMutation.isPending}
                  className="w-full"
                >
                  {permissionsMutation.isPending
                    ? "Aplicando..."
                    : `Aplicar Permissoes (${selectedCpfs.size})`}
                </Button>

                {lastBatchCpfs.length > 0 && (
                  <Button
                    variant="outline"
                    onClick={handleUndo}
                    disabled={undoMutation.isPending}
                    className="w-full"
                  >
                    <Undo2 className="h-4 w-4 mr-2" />
                    {undoMutation.isPending
                      ? "Desfazendo..."
                      : `Desfazer ultima acao (${lastBatchCpfs.length})`}
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
