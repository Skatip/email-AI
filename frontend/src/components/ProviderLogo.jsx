export default function ProviderLogo({ type = "gmail", size = 28, className = "" }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 48 48",
    className: `providerLogo providerLogo-${type} ${className}`.trim(),
    role: "img",
    "aria-label": `${type} logo`,
  };

  if (type === "gmail") {
    return (
      <svg {...common}>
        <rect width="48" height="48" rx="12" fill="#fff" />
        <path d="M8 14v22h7V21.8L24 29l9-7.2V36h7V14l-16 12L8 14z" fill="#EA4335" />
        <path d="M8 14l16 12 16-12v-2.5C40 9.6 37.8 8.5 36.3 9.7L24 19 11.7 9.7C10.2 8.5 8 9.6 8 11.5V14z" fill="#C5221F" />
        <path d="M8 14v22h7V19.2L8 14z" fill="#4285F4" />
        <path d="M40 14v22h-7V19.2L40 14z" fill="#34A853" />
        <path d="M15 19.2V36h18V19.2L24 26l-9-6.8z" fill="#FBBC04" opacity="0.18" />
      </svg>
    );
  }

  if (type === "outlook") {
    return (
      <svg {...common}>
        <rect width="48" height="48" rx="12" fill="#F3F7FF" />
        <rect x="18" y="10" width="22" height="28" rx="3" fill="#0A5BD3" />
        <rect x="21" y="13" width="17" height="8" rx="1.5" fill="#38A1F3" />
        <rect x="21" y="23" width="17" height="12" rx="1.5" fill="#1D75D8" />
        <rect x="7" y="15" width="23" height="22" rx="4" fill="#0078D4" />
        <path d="M13.8 21.5c1.4-1.5 3.2-2.2 5.3-2.2s3.9.7 5.3 2.2c1.4 1.5 2.1 3.4 2.1 5.7s-.7 4.2-2.1 5.7c-1.4 1.5-3.2 2.2-5.3 2.2s-3.9-.7-5.3-2.2c-1.4-1.5-2.1-3.4-2.1-5.7s.7-4.2 2.1-5.7zm2.8 8.9c.6.8 1.4 1.2 2.5 1.2s1.9-.4 2.5-1.2c.6-.8.9-1.9.9-3.2s-.3-2.4-.9-3.2c-.6-.8-1.4-1.2-2.5-1.2s-1.9.4-2.5 1.2c-.6.8-.9 1.9-.9 3.2s.3 2.4.9 3.2z" fill="#fff" />
      </svg>
    );
  }

  if (type === "slack") {
    return (
      <svg {...common}>
        <rect width="48" height="48" rx="12" fill="#fff" />
        <path d="M18.2 8a4.2 4.2 0 0 1 4.2 4.2v10.1h-4.2A4.2 4.2 0 0 1 14 18.1v-5.9A4.2 4.2 0 0 1 18.2 8z" fill="#36C5F0" />
        <path d="M8 18.2a4.2 4.2 0 0 1 4.2-4.2h4.2v4.2a4.2 4.2 0 0 1-4.2 4.2H12.2A4.2 4.2 0 0 1 8 18.2z" fill="#36C5F0" />
        <path d="M40 18.2a4.2 4.2 0 0 1-4.2 4.2H25.7v-4.2a4.2 4.2 0 0 1 4.2-4.2h5.9A4.2 4.2 0 0 1 40 18.2z" fill="#2EB67D" />
        <path d="M29.8 8a4.2 4.2 0 0 1 4.2 4.2v4.2h-4.2a4.2 4.2 0 0 1-4.2-4.2v-.1A4.2 4.2 0 0 1 29.8 8z" fill="#2EB67D" />
        <path d="M29.8 40a4.2 4.2 0 0 1-4.2-4.2V25.7h4.2A4.2 4.2 0 0 1 34 29.9v5.9A4.2 4.2 0 0 1 29.8 40z" fill="#ECB22E" />
        <path d="M40 29.8a4.2 4.2 0 0 1-4.2 4.2h-4.2v-4.2a4.2 4.2 0 0 1 4.2-4.2h.1A4.2 4.2 0 0 1 40 29.8z" fill="#ECB22E" />
        <path d="M8 29.8a4.2 4.2 0 0 1 4.2-4.2h10.1v4.2A4.2 4.2 0 0 1 18.1 34h-5.9A4.2 4.2 0 0 1 8 29.8z" fill="#E01E5A" />
        <path d="M18.2 40a4.2 4.2 0 0 1-4.2-4.2v-4.2h4.2a4.2 4.2 0 0 1 4.2 4.2v.1A4.2 4.2 0 0 1 18.2 40z" fill="#E01E5A" />
      </svg>
    );
  }

  if (type === "jira") {
    return (
      <svg {...common}>
        <rect width="48" height="48" rx="12" fill="#F4F8FF" />
        <path d="M25.2 8.8 39.2 22.8 25.2 36.8c-1.2 1.2-3.1 1.2-4.3 0l-5.6-5.6 8.4-8.4-8.4-8.4 5.6-5.6c1.2-1.2 3.1-1.2 4.3 0z" fill="#2684FF" />
        <path d="M22.8 14.5 31.1 22.8 22.8 31.1 14.5 22.8 22.8 14.5z" fill="#0052CC" />
        <path d="M14.4 14.4 22.8 22.8 14.4 31.2 8.8 25.6c-1.2-1.2-1.2-3.1 0-4.3l5.6-6.9z" fill="#0065FF" />
      </svg>
    );
  }

  return null;
}
