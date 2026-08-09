import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConvexProvider, ConvexReactClient } from "convex/react";
import App from "./App";
import "./styles.css";

const convexUrl = import.meta.env.VITE_CONVEX_URL as string | undefined;
const root = createRoot(document.getElementById("root")!);

if (convexUrl) {
  const convex = new ConvexReactClient(convexUrl);

  root.render(
    <StrictMode>
      <ConvexProvider client={convex}>
        <App convexEnabled />
      </ConvexProvider>
    </StrictMode>
  );
} else {
  root.render(
    <StrictMode>
      <App convexEnabled={false} />
    </StrictMode>
  );
}
