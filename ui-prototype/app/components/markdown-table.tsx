import { CitationText } from "./citation-text";

export function MarkdownTable({ markdown }: { markdown: string }) {
  const rows = markdown.trim().split("\n").filter(line => line.startsWith("|"))
    .map(line => line.split("|").slice(1, -1).map(cell => cell.trim()));
  if (rows.length < 3) return null;
  return <div className="table-scroll"><table>
    <thead><tr>{rows[0].map((cell, i) => <th key={i}><CitationText text={cell} /></th>)}</tr></thead>
    <tbody>{rows.slice(2).map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}><CitationText text={cell} /></td>)}</tr>)}</tbody>
  </table></div>;
}
