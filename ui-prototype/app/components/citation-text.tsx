export function CitationText({ text }: { text: string }) {
  return <>{text.split(/(\[Doc_[^\]\n]+\])/g).map((part, index) =>
    part.startsWith("[Doc_") && part.endsWith("]")
      ? <span className="citation" title={`Nguồn: ${part.slice(1, -1)}`} key={index}>{part}</span>
      : part)}</>;
}
