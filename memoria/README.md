# Memoria LaTeX

Plantilla inicial de la memoria del TFM.

## Compilacion

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
- `capitulos/`: capitulos de la memoria.
- `bibliografia/referencias.bib`: referencias BibTeX.
- `figuras/`, `tablas/`, `anexos/`: artefactos academicos auxiliares.

## Criterio de actualizacion

Cada avance tecnico debe reflejar:

- que se ha hecho;
- por que se ha elegido;
- como se ha validado;
- que limitaciones quedan.
