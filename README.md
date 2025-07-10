## Documentação

Necessário conexão com a internet para rodar o programa pela primeira vez, ter Python instalado e um banco de dados com a seguinte configuração:

-- Trabalho.fornecedores definição

CREATE TABLE `fornecedores` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  `fornecedores_endereco` varchar(100) DEFAULT NULL,
  `fornecedores_numerobalanca` int(11) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=207 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;


-- Trabalho.produtos definição

CREATE TABLE `produtos` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `nome` varchar(100) NOT NULL,
  `preco_base` decimal(10,2) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;


-- Trabalho.usuarios definição

CREATE TABLE `usuarios` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `senha_hash` varchar(255) NOT NULL,
  `nome` varchar(100) DEFAULT NULL,
  `nivel` enum('admin','gerente','operador','consulta') NOT NULL DEFAULT 'operador',
  `ativo` tinyint(1) DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;


-- Trabalho.categorias_fornecedor_por_fornecedor definição

CREATE TABLE `categorias_fornecedor_por_fornecedor` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fornecedor_id` int(11) NOT NULL,
  `nome` varchar(100) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `fornecedor_id` (`fornecedor_id`,`nome`),
  CONSTRAINT `categorias_fornecedor_por_fornecedor_ibfk_1` FOREIGN KEY (`fornecedor_id`) REFERENCES `fornecedores` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=257 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;


-- Trabalho.dados_bancarios_fornecedor definição

CREATE TABLE `dados_bancarios_fornecedor` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fornecedor_id` int(11) DEFAULT NULL,
  `banco` varchar(100) DEFAULT NULL,
  `CPFouCNPJ` varchar(18) DEFAULT NULL,
  `agencia` varchar(20) DEFAULT NULL,
  `conta` varchar(20) DEFAULT NULL,
  `padrao` tinyint(1) DEFAULT 0,
  `nome_conta` varchar(100) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fornecedor_id` (`fornecedor_id`),
  CONSTRAINT `dados_bancarios_fornecedor_ibfk_1` FOREIGN KEY (`fornecedor_id`) REFERENCES `fornecedores` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;


-- Trabalho.ajustes_fixos_produto_fornecedor_categoria definição

CREATE TABLE `ajustes_fixos_produto_fornecedor_categoria` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `produto_id` int(11) NOT NULL,
  `categoria_id` int(11) NOT NULL,
  `ajuste_fixo` decimal(10,2) DEFAULT 0.00,
  PRIMARY KEY (`id`),
  UNIQUE KEY `produto_id` (`produto_id`,`categoria_id`),
  KEY `categoria_id` (`categoria_id`),
  CONSTRAINT `ajustes_fixos_produto_fornecedor_categoria_ibfk_1` FOREIGN KEY (`produto_id`) REFERENCES `produtos` (`id`),
  CONSTRAINT `ajustes_fixos_produto_fornecedor_categoria_ibfk_2` FOREIGN KEY (`categoria_id`) REFERENCES `categorias_fornecedor_por_fornecedor` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2057 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;


-- Trabalho.compras definição

CREATE TABLE `compras` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fornecedor_id` int(11) DEFAULT NULL,
  `data_compra` date DEFAULT NULL,
  `valor_abatimento` decimal(10,2) DEFAULT 0.00,
  `total` decimal(10,2) DEFAULT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'Criada',
  `dados_bancarios_id` int(11) DEFAULT NULL,
  `tipo` enum('compra','venda','transacao') NOT NULL DEFAULT 'compra',
  `direcao` enum('entrada','saida') DEFAULT NULL,
  `descricao` varchar(255) DEFAULT NULL,
  `origem` varchar(20) DEFAULT 'compras',
  `considerar_no_saldo_movimentacao` tinyint(1) DEFAULT 1,
  PRIMARY KEY (`id`),
  KEY `fornecedor_id` (`fornecedor_id`),
  KEY `fk_compra_dados_bancarios` (`dados_bancarios_id`),
  CONSTRAINT `compras_ibfk_1` FOREIGN KEY (`fornecedor_id`) REFERENCES `fornecedores` (`id`),
  CONSTRAINT `fk_compra_dados_bancarios` FOREIGN KEY (`dados_bancarios_id`) REFERENCES `dados_bancarios_fornecedor` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=41 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;


-- Trabalho.debitos_fornecedores definição

CREATE TABLE `debitos_fornecedores` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `fornecedor_id` int(11) DEFAULT NULL,
  `data_lancamento` date DEFAULT NULL,
  `descricao` text DEFAULT NULL,
  `valor` decimal(10,2) DEFAULT NULL,
  `tipo` varchar(10) DEFAULT NULL,
  `compra_id` int(11) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_debitos_fornecedores_fornecedor` (`fornecedor_id`),
  KEY `fk_debitos_fornecedores_compra` (`compra_id`),
  CONSTRAINT `debitos_fornecedores_ibfk_1` FOREIGN KEY (`fornecedor_id`) REFERENCES `fornecedores` (`id`),
  CONSTRAINT `debitos_fornecedores_ibfk_2` FOREIGN KEY (`compra_id`) REFERENCES `compras` (`id`),
  CONSTRAINT `fk_debitos_fornecedores_compra` FOREIGN KEY (`compra_id`) REFERENCES `compras` (`id`),
  CONSTRAINT `fk_debitos_fornecedores_fornecedor` FOREIGN KEY (`fornecedor_id`) REFERENCES `fornecedores` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=42 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;


-- Trabalho.itens_compra definição

CREATE TABLE `itens_compra` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `compra_id` int(11) DEFAULT NULL,
  `produto_id` int(11) DEFAULT NULL,
  `quantidade` int(11) DEFAULT NULL,
  `preco_unitario` decimal(10,2) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `compra_id` (`compra_id`),
  KEY `produto_id` (`produto_id`),
  CONSTRAINT `itens_compra_ibfk_1` FOREIGN KEY (`compra_id`) REFERENCES `compras` (`id`),
  CONSTRAINT `itens_compra_ibfk_2` FOREIGN KEY (`produto_id`) REFERENCES `produtos` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=90 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_uca1400_ai_ci;
