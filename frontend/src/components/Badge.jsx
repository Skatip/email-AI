export function Badge({ children, tone = "gray" }) {
  const map = {
    red: "bg-red-100 text-red-800 border-red-200",
    yellow: "bg-yellow-100 text-yellow-800 border-yellow-200",
    green: "bg-green-100 text-green-800 border-green-200",
    blue: "bg-blue-100 text-blue-800 border-blue-200",
    gray: "bg-gray-100 text-gray-800 border-gray-200",
    purple: "bg-purple-100 text-purple-800 border-purple-200",
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${map[tone] || map.gray}`}
    >
      {children}
    </span>
  );
}