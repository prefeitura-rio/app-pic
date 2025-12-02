export const bairros = [
  "Madureira", "Bangu", "Campo Grande", "Tijuca", "Copacabana",
  "Ipanema", "Barra da Tijuca", "Jacarepaguá", "Vila Isabel", "Méier",
  "Penha", "Ilha do Governador", "Santa Cruz", "Realengo", "Pavuna",
  "Maré", "Rocinha", "Vidigal", "Cidade de Deus", "Anchieta"
];

// Coordenadorias de Atenção Primária (Saúde)
export const coordenadoriasCAP: Record<string, string[]> = {
  "CAP 1.0": [],
  "CAP 2.1": ["Copacabana", "Ipanema", "Rocinha", "Vidigal"],
  "CAP 2.2": ["Tijuca", "Vila Isabel"],
  "CAP 3.1": ["Penha", "Ilha do Governador", "Maré"],
  "CAP 3.2": ["Méier", "Madureira"],
  "CAP 3.3": ["Pavuna", "Anchieta"],
  "CAP 4.0": ["Barra da Tijuca", "Jacarepaguá", "Cidade de Deus"],
  "CAP 5.1": ["Bangu", "Realengo"],
  "CAP 5.2": ["Campo Grande"],
  "CAP 5.3": ["Santa Cruz"]
};

// Coordenadorias Regionais de Educação
export const coordenadoriasCRE: Record<string, string[]> = {
  "2ª CRE": ["Copacabana", "Ipanema", "Rocinha", "Vidigal"],
  "3ª CRE": ["Tijuca", "Vila Isabel", "Méier"],
  "4ª CRE": ["Barra da Tijuca", "Jacarepaguá", "Cidade de Deus"],
  "5ª CRE": ["Bangu", "Realengo"],
  "6ª CRE": ["Campo Grande"],
  "7ª CRE": ["Santa Cruz"],
  "8ª CRE": ["Penha", "Ilha do Governador"],
  "9ª CRE": ["Madureira"],
  "10ª CRE": ["Pavuna", "Anchieta"],
  "11ª CRE": ["Maré"]
};

// Coordenadorias Regionais de Assistência Social (CAS)
export const coordenadoriasCRAS: Record<string, string[]> = {
  "1ª CAS Centro": [],
  "2ª CAS Vila Isabel, Grande Tijuca e Zona Sul": ["Vila Isabel", "Tijuca", "Copacabana", "Ipanema", "Rocinha", "Vidigal"],
  "3ª CAS Engenho Novo": ["Méier"],
  "4ª CAS Bonsucesso": ["Penha", "Ilha do Governador", "Maré"],
  "5ª CAS Madureira": ["Madureira"],
  "6ª CAS Irajá": ["Pavuna", "Anchieta"],
  "7ª CAS Jacarepaguá": ["Barra da Tijuca", "Jacarepaguá", "Cidade de Deus"],
  "8ª CAS Bangu": ["Bangu", "Realengo"],
  "9ª CAS Campo Grande": ["Campo Grande"],
  "10ª CAS Santa Cruz": ["Santa Cruz"]
};

export const unidadesPorBairro: Record<string, string[]> = {
  Madureira: ["ESF Vila Esperança", "CRAS Madureira", "Creche Pequenos Passos"],
  Bangu: ["Clínica da Família Bangu", "CRAS Bangu", "EDI Mundo Feliz"],
  "Campo Grande": ["ESF Campo Grande", "CRAS Cosmos", "Creche Esperança"],
  Tijuca: ["CF Tijuca", "CRAS Praça Saens Peña", "Creche Alegria"],
  Copacabana: ["ESF Copacabana", "CRAS Copa", "EDI Praia"],
  Ipanema: ["CF Ipanema", "CRAS Zona Sul", "Creche Arpoador"],
  "Barra da Tijuca": ["ESF Barra", "CRAS Barra", "EDI Recreio"],
  Jacarepaguá: ["CF Jacarepaguá", "CRAS Freguesia", "Creche Unidos"],
  "Vila Isabel": ["ESF Vila Isabel", "CRAS Boulevard", "EDI Grajaú"],
  Méier: ["CF Méier", "CRAS Todos os Santos", "Creche Amanhã"],
  Penha: ["ESF Penha", "CRAS Penha Circular", "EDI Brás de Pina"],
  "Ilha do Governador": ["CF Ilha", "CRAS Portuguesa", "Creche Mar"],
  "Santa Cruz": ["ESF Santa Cruz", "CRAS Paciência", "EDI Sepetiba"],
  Realengo: ["CF Realengo", "CRAS Padre Miguel", "Creche Esperança"],
  Pavuna: ["ESF Pavuna", "CRAS Pavuna", "EDI Acari"],
  Maré: ["CF Maré", "CRAS Nova Holanda", "Creche Bonsucesso"],
  Rocinha: ["ESF Rocinha", "CRAS Rocinha", "EDI São Conrado"],
  Vidigal: ["CF Vidigal", "CRAS Vidigal", "Creche Leblon"],
  "Cidade de Deus": ["ESF CDD", "CRAS Cidade de Deus", "EDI Jacarepaguá"],
  Anchieta: ["CF Anchieta", "CRAS Ricardo de Albuquerque", "Creche Guadalupe"]
};
