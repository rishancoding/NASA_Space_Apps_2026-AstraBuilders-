import Markdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

// Keep generated HTML inert, block unsafe URLs, and avoid remote tracking images.
export default function ChatMarkdown({ children }) {
  return <div className="chat-markdown">
    <Markdown remarkPlugins={[remarkGfm]} skipHtml
      urlTransform={(url) => /^https?:\/\//i.test(url) || url.startsWith("#") ? defaultUrlTransform(url) : ""}
      components={{
        a: ({ href, children }) => href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>,
        img: ({ alt }) => <span>{alt}</span>,
        table: ({ children }) => <div className="chat-table-scroll" tabIndex={0} role="region" aria-label="Assistant table"><table>{children}</table></div>,
      }}>{children}</Markdown>
  </div>;
}
