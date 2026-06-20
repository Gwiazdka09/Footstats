// Polska odmiana rzeczownika "typ" (1 typ / 2-4 typy / 5+ typów)
export const odmianaTypy = (n) => {
  if (n === 1) return "1 typ";
  const ostatnia = n % 10;
  const dwieOstatnie = n % 100;
  if (ostatnia >= 2 && ostatnia <= 4 && !(dwieOstatnie >= 12 && dwieOstatnie <= 14)) return `${n} typy`;
  return `${n} typów`;
};

const TIP_CATEGORIES = [
  { label: "Wynik meczu (1X2)", match: (t) => ["1", "1X", "X", "X2", "2"].includes(t.tip) },
  { label: "Obie strzelają", match: (t) => t.tip.startsWith("BTTS") },
  { label: "Liczba goli", match: (t) => /^(Over|Under)/.test(t.tip) },
];

export const groupTips = (tips) => {
  const used = new Set();
  const groups = TIP_CATEGORIES.map((cat) => {
    const items = tips.filter((t) => cat.match(t));
    items.forEach((t) => used.add(t));
    return { label: cat.label, items };
  }).filter((g) => g.items.length > 0);
  const rest = tips.filter((t) => !used.has(t));
  if (rest.length > 0) groups.push({ label: "Inne", items: rest });
  return groups;
};
