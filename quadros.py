"""Extrai quadros de um vídeo para que uma IA com visão leia a tela.

Existe para o caso que a legenda não resolve: vídeo **sem fala**. Captura de
tela de terminal, demonstração muda, gravação de procedimento sem narração —
o YouTube não gera legenda porque não há o que transcrever, mas a informação
está toda ali, escrita na tela.

A alternativa seria mandar o vídeo para um modelo de compreensão de vídeo
hospedado (TwelveLabs e afins). Aqui a escolha é local, por três motivos
concretos:

- o `ffmpeg` já está instalado e não custa nada;
- vídeo interno costuma ter dado sensível na tela (a gravação que motivou
  este módulo exibe um nome de usuário no prompt de autenticação) — subir
  para terceiro seria vazamento;
- para texto em terminal, ler o quadro é melhor que descrever a cena: um
  modelo de vídeo diria "um terminal com texto branco"; lendo o quadro se
  obtém o comando digitado e a resposta que apareceu.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def ffmpeg_disponivel() -> bool:
    return shutil.which("ffmpeg") is not None


def duracao_segundos(video: Path) -> float | None:
    """Duração via ffprobe. None se não der para determinar."""
    if not shutil.which("ffprobe"):
        return None
    resultado = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(resultado.stdout.strip())
    except ValueError:
        return None


def tem_audio(video: Path) -> bool:
    """Diz se o vídeo tem faixa de áudio — se não tiver, não existe
    transcrição possível e extrair quadros é o único caminho."""
    if not shutil.which("ffprobe"):
        return True          # na dúvida, não afirma que é mudo
    resultado = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(video),
        ],
        capture_output=True, text=True,
    )
    return "audio" in resultado.stdout


def extrair(video: Path, destino: Path, intervalo: int = 4,
            largura: int = 1280) -> list[Path]:
    """Grava um quadro a cada `intervalo` segundos em `destino`.

    `largura` faz upscale: gravação de tela costuma vir pequena (a que
    motivou este módulo tem 494x324) e ampliar deixa o texto do terminal
    bem mais legível. Só amplia, nunca reduz.
    """
    if not ffmpeg_disponivel():
        sys.exit(
            "ffmpeg não encontrado no PATH.\n"
            "instale com: winget install Gyan.FFmpeg"
        )

    destino.mkdir(parents=True, exist_ok=True)
    for antigo in destino.glob("quadro_*.jpg"):
        antigo.unlink()

    # scale com -1 preserva a proporção; min() evita ampliar além do útil
    filtro = f"fps=1/{intervalo},scale='min({largura},iw*3)':-1:flags=lanczos"

    resultado = subprocess.run(
        [
            "ffmpeg", "-loglevel", "error",
            "-i", str(video),
            "-vf", filtro,
            "-q:v", "3",
            str(destino / "quadro_%03d.jpg"),
        ],
        capture_output=True, text=True,
    )
    if resultado.returncode != 0:
        sys.exit(f"ffmpeg falhou:\n{resultado.stderr.strip()}")

    return sorted(destino.glob("quadro_*.jpg"))


def extrair_com_relatorio(video: Path, destino: Path,
                          intervalo: int = 4) -> dict:
    """Extrai e devolve um resumo pronto para o MCP ou para a linha de
    comando, incluindo o instante de cada quadro."""
    duracao = duracao_segundos(video)
    arquivos = extrair(video, destino, intervalo)

    return {
        "video": str(video),
        "duracao_segundos": duracao,
        "tem_audio": tem_audio(video),
        "intervalo_segundos": intervalo,
        "quadros": [
            {
                "arquivo": str(a),
                "instante": f"{(i * intervalo) // 60:02d}:{(i * intervalo) % 60:02d}",
            }
            for i, a in enumerate(arquivos)
        ],
    }


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Extrai quadros de um vídeo para leitura por IA com visão.",
    )
    ap.add_argument("video", help="arquivo de vídeo")
    ap.add_argument("--saida", default="quadros", help="pasta de destino")
    ap.add_argument("--intervalo", type=int, default=4,
                    help="segundos entre quadros (padrão: 4)")
    args = ap.parse_args()

    video = Path(args.video)
    if not video.exists():
        sys.exit(f"arquivo não encontrado: {video}")

    relatorio = extrair_com_relatorio(video, Path(args.saida), args.intervalo)

    if relatorio["duracao_segundos"]:
        print(f"duração: {relatorio['duracao_segundos']:.0f}s", end="  ")
    print(f"áudio: {'sim' if relatorio['tem_audio'] else 'NÃO (vídeo mudo)'}")
    print(f"\n{len(relatorio['quadros'])} quadro(s):\n")
    for quadro in relatorio["quadros"]:
        print(f"  ({quadro['instante']})  {Path(quadro['arquivo']).name}")
    print(f"\nsaída: {Path(args.saida).resolve()}")


if __name__ == "__main__":
    main()
