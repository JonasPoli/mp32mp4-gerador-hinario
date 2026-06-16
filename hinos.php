<?php

$arquivoJson = 'hinos.json';
$conteudoJson = file_get_contents($arquivoJson);
$hinos = json_decode($conteudoJson, true);

$pastaDestino = 'hinos_txt';

if (!is_dir($pastaDestino)) {
    mkdir($pastaDestino);
}

foreach ($hinos as $hino) {
    $numero = str_pad($hino['numero'], 3, '0', STR_PAD_LEFT);
    $titulo = $hino['titulo'];
    $letra = $hino['letra'];

    $nomeArquivo = $pastaDestino . '/hino_' . $numero . '.txt';
    $conteudoArquivo = "Hino " . $numero . " - " . $titulo . "\n\n";

    if (is_array($letra)) {
        $conteudoArquivo .= implode("\n\n", $letra);
    } else {
        $conteudoArquivo .= $letra;
    }

    file_put_contents($nomeArquivo, $conteudoArquivo);
    echo "Arquivo criado: " . $nomeArquivo . "\n";
}

echo "Processo concluído.";
?>