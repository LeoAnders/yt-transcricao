"""Testes de `limpar.py` — conversão do `.vtt` rolante em texto legível.

Puro: recebe arquivo/texto, devolve texto. Nenhuma rede envolvida.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import limpar  # noqa: E402


class TestNomeDoArquivo(unittest.TestCase):
    """O nome do `.vtt` é a única fonte do id e do título do vídeo."""

    def _nome(self, arquivo: str) -> tuple[str, str]:
        return limpar.nome_do_arquivo(Path(arquivo))

    def test_separa_id_e_titulo(self) -> None:
        self.assertEqual(
            self._nome("dQw4w9WgXcQ - Aula de HLS.pt.vtt"),
            ("dQw4w9WgXcQ", "Aula de HLS"),
        )

    def test_remove_sufixo_orig(self) -> None:
        self.assertEqual(
            self._nome("dQw4w9WgXcQ - Aula de HLS.pt-orig.vtt")[1], "Aula de HLS"
        )

    def test_remove_codigo_de_idioma_com_digito(self) -> None:
        """Regressão de 2026-08-21.

        Legenda traduzida sai como `.pt-es-419`; o padrão antigo
        (`[a-zA-Z-]+`) não casava por causa do `419` e o título chegava na
        interface como "Never Gonna Give You Up (4K Remaster).pt-es-419".
        """
        for sufixo in ("pt-es-419", "es-419", "zh-Hans", "pt-BR", "en-US"):
            with self.subTest(sufixo=sufixo):
                nome = f"dQw4w9WgXcQ - Never Gonna Give You Up (4K Remaster).{sufixo}.vtt"
                self.assertEqual(
                    self._nome(nome)[1], "Never Gonna Give You Up (4K Remaster)"
                )

    def test_preserva_titulo_que_termina_em_ponto_e_palavra(self) -> None:
        # "Final" tem 5 letras: não é código de idioma e não pode ser cortado.
        self.assertEqual(
            self._nome("abc12345678 - Curso de HLS - Ep. Final.pt.vtt")[1],
            "Curso de HLS - Ep. Final",
        )

    def test_preserva_versao_no_titulo(self) -> None:
        self.assertEqual(
            self._nome("abc12345678 - Migração para a v2.1.pt.vtt")[1],
            "Migração para a v2.1",
        )

    def test_titulo_com_hifen_usa_o_primeiro_separador(self) -> None:
        self.assertEqual(
            self._nome("abc12345678 - Parte 1 - Introdução.pt.vtt"),
            ("abc12345678", "Parte 1 - Introdução"),
        )

    def test_sem_titulo_usa_o_id(self) -> None:
        self.assertEqual(self._nome("abc12345678.pt.vtt"), ("abc12345678", "abc12345678"))


class TestExtrairFalas(unittest.TestCase):
    def test_remove_tags_inline_e_repeticao(self) -> None:
        vtt = (
            "WEBVTT\nKind: captions\nLanguage: pt\n\n"
            "00:00:00.000 --> 00:00:02.000\nprimeira <c>linha</c>\n\n"
            "00:00:02.000 --> 00:00:04.000\nprimeira linha\n"
            "segunda <00:00:03.000>linha\n"
        )
        falas = limpar.extrair_falas(vtt)
        self.assertEqual(falas, [(0, "primeira linha"), (2, "segunda linha")])

    def test_ignora_cabecalhos_e_linhas_vazias(self) -> None:
        self.assertEqual(limpar.extrair_falas("WEBVTT\n\nKind: captions\n\n"), [])


class TestAgrupar(unittest.TestCase):
    def test_abre_paragrafo_a_cada_janela(self) -> None:
        falas = [(0, "a"), (10, "b"), (35, "c"), (70, "d")]
        self.assertEqual(
            limpar.agrupar(falas), [(0, "a b"), (35, "c"), (70, "d")]
        )

    def test_lista_vazia(self) -> None:
        self.assertEqual(limpar.agrupar([]), [])


class TestMontarCorpo(unittest.TestCase):
    def test_com_timestamps(self) -> None:
        self.assertEqual(
            limpar.montar_corpo([(0, "a"), (222, "b")]), "(00:00) a\n\n(03:42) b"
        )

    def test_sem_timestamps(self) -> None:
        self.assertEqual(limpar.montar_corpo([(0, "a"), (222, "b")], False), "a\n\nb")


if __name__ == "__main__":
    unittest.main()
