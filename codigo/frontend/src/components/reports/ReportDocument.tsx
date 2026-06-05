import { useMemo } from "react";

export function MarkdownDocumentPreview({
  document,
  emptyText,
  kicker,
}: {
  document: string | null;
  emptyText: string;
  kicker: string;
}) {
  if (document === null) {
    return (
      <div className="report-document empty-report-document">
        <p className="empty-state compact-empty">{emptyText}</p>
      </div>
    );
  }
  return <ReportDocument report={document} kicker={kicker} />;
}

function ReportDocument({ report, kicker }: { report: string; kicker: string }) {
  const document = useMemo(() => parseReportDocument(report, kicker), [report, kicker]);

  return (
    <article className="report-document">
      <header className="report-document-header">
        <p>{document.kicker}</p>
        <h4>{document.title}</h4>
        {document.meta.length > 0 ? (
          <dl className="report-meta-grid">
            {document.meta.map((item) => (
              <div key={item.label}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </header>

      <div className="report-section-stack">
        {document.sections.map((section) => (
          <section className="report-document-section" key={section.title}>
            <h5>{section.title}</h5>
            <ReportBlocks lines={section.lines} />
          </section>
        ))}
      </div>
    </article>
  );
}

function ReportBlocks({ lines }: { lines: string[] }) {
  const blocks = reportBlocks(lines);
  if (blocks.length === 0) {
    return <p className="empty-state compact-empty">Sin contenido visible</p>;
  }

  return (
    <>
      {blocks.map((block, index) => {
        if (block.kind === "list") {
          return (
            <ul className="report-list" key={`list-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${item}-${itemIndex}`}>{inlineReportText(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.kind === "subheading") {
          return <h6 key={`heading-${index}`}>{block.text}</h6>;
        }
        return <p key={`paragraph-${index}`}>{inlineReportText(block.text)}</p>;
      })}
    </>
  );
}

interface ParsedReportDocument {
  kicker: string;
  title: string;
  meta: Array<{ label: string; value: string }>;
  sections: Array<{ title: string; lines: string[] }>;
}

type ReportBlock =
  | { kind: "paragraph"; text: string }
  | { kind: "subheading"; text: string }
  | { kind: "list"; items: string[] };

function parseReportDocument(report: string, fallbackKicker: string): ParsedReportDocument {
  const rawLines = report.split(/\r?\n/);
  const titleLine = rawLines.find((line) => line.trim().startsWith("# "));
  const title = titleLine
    ? stripMarkdown(titleLine.replace(/^#\s+/, ""))
    : "Informe tecnico de deteccion de anomalias";
  const sections: Array<{ title: string; lines: string[] }> = [];
  const introLines: string[] = [];
  let currentSection: { title: string; lines: string[] } | null = null;

  for (const rawLine of sanitizedReportLines(rawLines)) {
    const line = rawLine.trimEnd();
    if (line.startsWith("# ")) {
      continue;
    }
    if (line.startsWith("## ")) {
      currentSection = {
        title: stripMarkdown(line.replace(/^##\s+/, "")),
        lines: [],
      };
      sections.push(currentSection);
      continue;
    }
    if (currentSection) {
      currentSection.lines.push(line);
    } else {
      introLines.push(line);
    }
  }

  return {
    kicker: fallbackKicker,
    title,
    meta: reportMeta(introLines),
    sections,
  };
}

function sanitizedReportLines(lines: string[]): string[] {
  const visible: string[] = [];
  let skippingTechnicalSources = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    const normalized = stripMarkdown(line).replace(/:$/, "").toLowerCase();
    if (normalized === "fuentes" || normalized === "referencias de evidencia") {
      skippingTechnicalSources = true;
      continue;
    }
    if (skippingTechnicalSources) {
      if (line === "") {
        skippingTechnicalSources = false;
      }
      continue;
    }
    if (containsLocalPath(line)) {
      continue;
    }
    visible.push(rawLine);
  }

  return visible;
}

function reportMeta(lines: string[]): Array<{ label: string; value: string }> {
  const allowedLabels = new Map([
    ["Run ID", "Run"],
    ["Dataset", "Dataset"],
    ["Objetivo", "Objetivo"],
  ]);

  return lines
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => line.replace(/^-\s+/, ""))
    .map((line) => {
      const separator = line.indexOf(":");
      if (separator < 0) {
        return null;
      }
      const rawLabel = stripMarkdown(line.slice(0, separator));
      const label = allowedLabels.get(rawLabel);
      if (!label) {
        return null;
      }
      const value = stripMarkdown(line.slice(separator + 1));
      return value ? { label, value } : null;
    })
    .filter((item): item is { label: string; value: string } => item !== null);
}

function reportBlocks(lines: string[]): ReportBlock[] {
  const blocks: ReportBlock[] = [];
  let pendingList: string[] = [];

  function flushList() {
    if (pendingList.length > 0) {
      blocks.push({ kind: "list", items: pendingList });
      pendingList = [];
    }
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      continue;
    }
    if (line.startsWith("- ")) {
      pendingList.push(line.replace(/^-\s+/, ""));
      continue;
    }
    flushList();
    if (line.endsWith(":") && line.length < 72) {
      blocks.push({ kind: "subheading", text: stripMarkdown(line.replace(/:$/, "")) });
    } else {
      blocks.push({ kind: "paragraph", text: stripMarkdown(line) });
    }
  }
  flushList();
  return blocks;
}

function inlineReportText(value: string): string {
  return stripMarkdown(value);
}

function stripMarkdown(value: string): string {
  return value
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .trim();
}

function containsLocalPath(value: string): boolean {
  return /(^|[\s`("'[])(codigo\/|\/home\/|\.{1,2}\/|[A-Za-z]:\\)/.test(value);
}
