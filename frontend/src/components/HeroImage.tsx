import { useState } from "react";

// URL-only Steam CDN artwork, tried in order; nothing is downloaded or stored by the app.
// Steam's recorded header URL comes first: newer apps only have hashed paths that cannot be
// derived from the AppID.
export function marketingImageUrls(appid: number, headerImage?: string | null): string[] {
  return [
    ...(headerImage ? [headerImage] : []),
    `https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/${appid}/header.jpg`,
    `https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/${appid}/capsule_616x353.jpg`,
    `https://cdn.akamai.steamstatic.com/steam/apps/${appid}/header.jpg`,
  ];
}

export const PLACEHOLDER_IMAGE =
  "data:image/svg+xml;charset=UTF-8," +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="600">' +
      '<rect width="1200" height="600" fill="#0d1420"/>' +
      '<text x="600" y="300" fill="#7f91aa" font-family="Arial" font-size="34" ' +
      'text-anchor="middle">Steam artwork unavailable</text></svg>',
  );

/** Mount with key={appid} so the fallback chain restarts for each game. */
export function HeroImage({ appid, name, headerImage }: { appid: number; name: string; headerImage?: string | null }) {
  const urls = marketingImageUrls(appid, headerImage);
  const [index, setIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const src = index < urls.length ? urls[index] : PLACEHOLDER_IMAGE;

  return (
    <img
      id="heroImage"
      className={`hero-image${loading ? " loading" : ""}`}
      alt={`${name} Steam artwork`}
      src={src}
      onLoad={() => setLoading(false)}
      onError={() => {
        if (index < urls.length) setIndex(index + 1);
        else setLoading(false);
      }}
    />
  );
}
