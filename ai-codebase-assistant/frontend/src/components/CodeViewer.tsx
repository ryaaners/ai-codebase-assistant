import { useEffect, useRef, useState } from "react";
import Editor, { type Monaco } from "@monaco-editor/react";
import type { editor as MonacoEditor } from "monaco-editor";
import { Loader2 } from "lucide-react";
import { api } from "@/api/client";
import type { FileContent } from "@/types";

interface Props {
  repoId: string;
  path: string;
  focusLine?: number | null;
}

const LANGUAGE_MAP: Record<string, string> = {
  python: "python",
  javascript: "javascript",
  typescript: "typescript",
  tsx: "typescript",
};

export default function CodeViewer({ repoId, path, focusLine }: Props) {
  const [file, setFile] = useState<FileContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const editorRef = useRef<MonacoEditor.IStandaloneCodeEditor | null>(null);
  const decorationsRef = useRef<MonacoEditor.IEditorDecorationsCollection | null>(null);

  useEffect(() => {
    setFile(null);
    setError(null);
    api
      .getFileContent(repoId, path)
      .then(setFile)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load file"));
  }, [repoId, path]);

  useEffect(() => {
    if (!file || !focusLine || !editorRef.current) return;
    const ed = editorRef.current;
    ed.revealLineInCenter(focusLine);
    decorationsRef.current?.clear();
    decorationsRef.current = ed.createDecorationsCollection([
      {
        range: { startLineNumber: focusLine, startColumn: 1, endLineNumber: focusLine, endColumn: 1 },
        options: { isWholeLine: true, className: "bg-accent-soft" },
      },
    ]);
  }, [file, focusLine]);

  function handleMount(editorInstance: MonacoEditor.IStandaloneCodeEditor, _monaco: Monaco) {
    editorRef.current = editorInstance;
    if (focusLine) {
      editorInstance.revealLineInCenter(focusLine);
    }
  }

  if (error) {
    return <div className="flex h-full items-center justify-center text-sm text-danger">{error}</div>;
  }

  if (!file) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="size-5 animate-spin text-text-faint" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border-soft bg-surface px-4 py-2">
        <span className="font-mono text-[12.5px] text-text-muted">{file.path}</span>
        {file.symbols.length > 0 && (
          <span className="text-xs text-text-faint">{file.symbols.length} symbols</span>
        )}
      </div>
      <div className="min-h-0 flex-1">
        <Editor
          height="100%"
          theme="vs-dark"
          language={file.language ? LANGUAGE_MAP[file.language] : "plaintext"}
          value={file.content}
          onMount={handleMount}
          options={{
            readOnly: true,
            minimap: { enabled: false },
            fontSize: 13,
            fontFamily: "'JetBrains Mono', ui-monospace, monospace",
            scrollBeyondLastLine: false,
            renderLineHighlight: "none",
            padding: { top: 12 },
          }}
        />
      </div>
    </div>
  );
}
