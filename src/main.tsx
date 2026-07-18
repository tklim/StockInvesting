import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConvexReactClient } from "convex/react";
import { ConvexAuthProvider } from "@convex-dev/auth/react";
import App from "./App";
import "./styles.css";

const convexUrl = import.meta.env.VITE_CONVEX_URL as string | undefined;
const root = createRoot(document.getElementById("root")!);

if (convexUrl) {
  const convex = new ConvexReactClient(convexUrl);

  root.render(
    <StrictMode>
      <ConvexAuthProvider client={convex}>
        <App convexEnabled />
      </ConvexAuthProvider>
    </StrictMode>
  );
} else {
  root.render(
    <StrictMode>
      <App convexEnabled={false} />
    </StrictMode>
  );
}
