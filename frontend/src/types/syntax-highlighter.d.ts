declare module 'react-syntax-highlighter' {
  import { FC, CSSProperties } from 'react';
  interface SyntaxHighlighterProps {
    language?: string;
    style?: Record<string, unknown>;
    children: string;
    customStyle?: CSSProperties;
    codeTagProps?: Record<string, unknown>;
    showLineNumbers?: boolean;
    lineNumberStyle?: CSSProperties;
    wrapLines?: boolean;
    wrapLongLines?: boolean;
    PreTag?: keyof JSX.IntrinsicElements | FC;
    CodeTag?: keyof JSX.IntrinsicElements | FC;
    [key: string]: unknown;
  }
  export const Prism: FC<SyntaxHighlighterProps>;
  export const Light: FC<SyntaxHighlighterProps>;
  export const PrismAsync: FC<SyntaxHighlighterProps>;
  export const PrismAsyncLight: FC<SyntaxHighlighterProps>;
  export const LightAsync: FC<SyntaxHighlighterProps>;
}

declare module 'react-syntax-highlighter/dist/esm/styles/prism' {
  export const vscDarkPlus: Record<string, unknown>;
  export const oneDark: Record<string, unknown>;
  export const tomorrow: Record<string, unknown>;
}


/* NOTE: ?????????? @reactflow/core|background|minimap shim ?
   react-force-graph-2d ?? shim ?? 2026-08-05 ???SD/???????:
   @reactflow/* ?????????? shim ????? API ??????;
   react-force-graph-2d ?? ConversationGraph ? ReactFlow ?????
   ????????? types/force-graph.d.ts?????????????
   react-syntax-highlighter shim? */
