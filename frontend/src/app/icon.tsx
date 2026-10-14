import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

/** Browser-tab icon: the split blue/green mark with the rising pulse. */
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          background: "linear-gradient(90deg, #2563eb 50%, #10b981 50%)",
          borderRadius: 8,
        }}
      >
        <svg width="32" height="32" viewBox="0 0 32 32">
          <path
            d="M8.6 20.8 L13.2 14.6 L17.6 18.4 L23.4 9.6"
            fill="none"
            stroke="#ffffff"
            strokeWidth="2.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="23.4" cy="9.6" r="2.6" fill="#ffffff" />
        </svg>
      </div>
    ),
    size,
  );
}
