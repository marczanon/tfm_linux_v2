# Memoria LaTeX

Plantilla inicial de la memoria del TFM.

## Compilación

Desde esta carpeta:

```bash
pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex
```

El PDF resultante se genera como `main.pdf`.

## Estructura

- `main.tex`: documento principal.
- `capitulos/`: capítulos de la memoria.
- `bibliografia/referencias.bib`: referencias BibTeX.
- `figuras/`, `tablas/`, `anexos/`: artefactos académicos auxiliares.

## Criterio de actualización

Cada avance técnico debe reflejar:

- que se ha hecho;
- por qué se ha elegido;
- cómo se ha validado;
- que limitaciones quedan.
