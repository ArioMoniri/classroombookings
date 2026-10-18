// E2EB-F18 (FIX-K): an SSO sign-in of an existing, unlinked account ends on "failed" (no enumeration, sign-in.md
// §6.3); every "failed" now also says how to link the method from the profile, so that person is not stuck.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider, useI18n } from "@/lib/i18n/provider";
import { errorBody } from "./sign-in-page";

function Body() {
  const { t } = useI18n();
  return <p data-testid="body">{errorBody("failed", t, { org: null, ref: "S-224", invited: null, signedIn: null }).text}</p>;
}

describe("errorBody failed", () => {
  it("adds the link hint after the reference code, the same for every refusal", () => {
    render(
      <I18nProvider initialLocale="tr">
        <Body />
      </I18nProvider>,
    );
    expect(screen.getByTestId("body")).toHaveTextContent("S-224");
    expect(screen.getByTestId("body")).toHaveTextContent("Profil › Güvenlik'ten bu giriş yöntemini bağlayın.");
  });
});
