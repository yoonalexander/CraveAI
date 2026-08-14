import { useEffect, useState } from "react";

import { fetchLegalCurrent, LegalCurrent } from "../api/product";
import { LEGAL_CONFIG, LEGAL_REVISION_FALLBACK } from "../config/legal";

const termsSections = (operatorName: string) => [
  ["1. Agreement to these Terms", `These Terms are an agreement between you and ${operatorName}, the operator of CraveAI. By creating an account, using AI chat or voice, or otherwise using CraveAI after being shown these Terms, you agree to them and acknowledge the Privacy Policy. If you do not agree, do not use the service.`],
  ["2. Eligibility", "CraveAI is intended only for people who are at least 18 years old and legally able to enter this agreement. Registration and guest AI access require an 18-or-older confirmation. Do not use CraveAI if you do not meet these requirements."],
  ["3. What CraveAI provides", "CraveAI is a restaurant-discovery service. It combines a user-confirmed map area, Google restaurant data, optional official-menu evidence, saved preferences, and AI-assisted interpretation and ranking. CraveAI does not sell food, accept reservations, place delivery orders, provide transportation or navigation, or act for any restaurant."],
  ["4. Accounts and authentication", "You may browse and use limited chat as a guest. Account features use Supabase authentication and may include email/password or Google sign-in. Give accurate account information, protect access to your email and account, and notify us if you suspect unauthorized use. You are responsible for activity through your account except where applicable law provides otherwise."],
  ["5. Your content and choices", "Prompts, collection names, notes, preferences, allergy or dietary entries, and feedback are user content. You retain any rights you have in that content and give CraveAI a limited permission to process it only as needed to provide, secure, maintain, and improve the service as described in the Privacy Policy. Do not submit content you lack the right to provide."],
  ["6. Acceptable use", "Do not use CraveAI unlawfully; harm, threaten, or impersonate others; attempt unauthorized access; bypass rate limits or safeguards; introduce malicious code; disrupt the service; scrape or permanently cache restricted provider content; reverse engineer protected components except where law permits; or use the service to create misleading, discriminatory, or dangerous outcomes."],
  ["7. AI-generated recommendations", "AI outputs and rankings are informational suggestions, not professional advice or guarantees. They can misunderstand a request or be incomplete, inaccurate, outdated, biased, unavailable, or unsuitable. A recommendation does not mean CraveAI or the operator endorses a restaurant. Independently assess whether any recommendation is appropriate for you."],
  ["8. Restaurant, map, and location information", "Restaurant names, locations, ratings, photos, menus, hours, prices, accessibility details, reservation or delivery options, routes, distances, and other venue information come from third parties or restaurant websites and can change without notice. CraveAI does not guarantee restaurant or menu-item availability, price, opening hours, travel or delivery time, quality, food safety, or the accuracy of map and location information. Confirm important details with the restaurant or relevant provider."],
  ["9. Allergies and dietary restrictions", "CraveAI is not a medical, nutritional, religious-certification, food-safety, or allergen-safety service. Menu evidence may be missing, stale, ambiguous, or affected by substitutions, shared equipment, cross-contact, or restaurant practices. CraveAI cannot guarantee that any restaurant, kitchen, menu item, or ingredient is safe or suitable for an allergy, intolerance, dietary restriction, or religious requirement. For serious allergies or medical needs, contact the restaurant directly and seek qualified professional advice rather than relying on CraveAI."],
  ["10. Saved places, History, preferences, and feedback", "Signed-in users may save Place IDs, collections, notes, preferences, and feedback. History is off by default; it is stored only after you enable it or explicitly save a conversation. You control these features through Likes, History, and Settings. Feedback is used for service quality measurement and does not automatically change personalized recommendations."],
  ["11. Usage limits", "Guest and Free plans have daily chat, Places-search, voice, feedback, and burst limits. Current plan limits are shown in the product or Pricing page and may be adjusted prospectively to protect security, reliability, and provider costs. Attempting to evade limits is prohibited."],
  ["12. Third-party services and external sites", "CraveAI depends on OpenAI, Google Maps and Places, Open-Meteo, Supabase, Vercel, Render, optional Google identity services, and official restaurant websites. Third-party content and services are controlled by their providers and may fail or change. External links are provided for convenience; CraveAI is not responsible for an external site, restaurant, or provider, and their separate terms and privacy practices apply."],
  ["13. Intellectual property", "CraveAI's original software, interface, branding, and content are owned by or licensed to the operator and are protected by applicable law. These Terms provide only a limited, revocable, non-transferable right to use CraveAI for its intended purpose. Google and other provider content remains owned by its respective provider or licensors."],
  ["14. Feedback about CraveAI", "If you send product suggestions or feedback, you allow the operator to use it without payment or obligation to implement it. This does not transfer ownership of private conversation content, saved notes, or other personal information, which remains governed by the Privacy Policy."],
  ["15. Suspension, termination, and account deletion", "You may stop using CraveAI at any time and may delete an account through Settings, subject to recent-authentication safeguards. The operator may restrict or end access where reasonably necessary for misuse, security, provider restrictions, legal obligations, or discontinuation. Account deletion removes account-owned application data and asks Supabase to delete the authentication account; limited de-identified or security records may remain where described in the Privacy Policy or required by law."],
  ["16. Availability and service changes", "CraveAI is provided on an as-available basis. Features may be interrupted, limited, changed, or discontinued, and provider outages can affect maps, weather, authentication, restaurant results, chat, or voice. Where reasonable, material service changes will be communicated through the product."],
  ["17. Disclaimers", "To the maximum extent permitted by law, CraveAI is provided without warranties, representations, conditions, or guarantees, whether express, implied, statutory, or collateral, including merchantability, fitness for a particular purpose, title, non-infringement, accuracy, availability, and uninterrupted or error-free operation. Rights that cannot lawfully be waived continue to apply."],
  ["18. Limitation of liability", "To the maximum extent permitted by law, the operator will not be liable for indirect, incidental, special, consequential, exemplary, or punitive damages, lost profits or data, personal decisions based on a recommendation, or harms arising from restaurant food, allergens, travel, third-party content, or provider outages. Nothing limits liability that applicable law does not allow to be limited."],
  ["19. Indemnity", "To the extent permitted by law, you agree to indemnify and hold the operator harmless from third-party claims, liabilities, damages, and reasonable costs arising from your unlawful misuse of CraveAI, your violation of these Terms, or content you submit without the necessary rights. This section does not apply where prohibited by consumer law."],
  ["20. Governing law", "These Terms are governed by the laws of the Province of Ontario and the federal laws of Canada applicable therein, without overriding mandatory consumer protections that apply in your place of residence. These Terms do not select an exclusive court or require arbitration."],
  ["21. Changes and contact", "The version and effective date appear at the top of this page. Signed-in users must acknowledge materially revised versions before continuing to protected features. For questions, use the support contact shown below."],
] as const;

const privacySections = (operatorName: string) => [
  ["1. Who operates CraveAI", `${operatorName} operates CraveAI from the address shown below and is responsible for the application-level personal information described in this Policy. This Policy applies to the CraveAI website, API, account features, restaurant discovery, AI chat, voice transcription, saved places, preferences, History, and feedback.`],
  ["2. Information you provide", "You may provide prompts and follow-up messages; collection names and notes; feedback and error reports; favorite cuisines and disliked foods; optional dietary restrictions, allergies, default location, search radius, recommendation preferences, and notification choices; and an 18-or-older confirmation. Do not put unnecessary sensitive information in a prompt, note, or voice recording."],
  ["3. Account and authentication information", "For an account, CraveAI processes your email address, Supabase user identifier, email-verification state, connected sign-in provider identifiers, policy versions accepted, acceptance timestamps, and an age-confirmed boolean. Passwords pass through the CraveAI backend to Supabase during account requests but are not written to CraveAI's application database or application logs. If you choose Google sign-in, Google and Supabase process the authentication exchange."],
  ["4. Location information", "With browser permission, CraveAI obtains precise device latitude and longitude. You may instead choose a place or address through Google autocomplete, move the map and confirm its visible bounds, or use the Toronto fallback. Current coordinates, bounds, radius, and a place label are used in memory to scope restaurant search, maps, weather, and later chat requests. They are not saved as chat messages. If you deliberately save a default location in Settings, its coordinates and label remain in your preference profile until changed, reset, or the account is deleted."],
  ["5. Restaurant, search, and recommendation data", "CraveAI processes confirmed map coordinates and bounds, search terms derived from your craving, filters, Google Place IDs and live venue details, restaurant candidates, ranking scores, evidence links, and recommendation tokens. New favorites persist only a Google Place ID plus your collection membership or note; current names, addresses, ratings, photos, hours, and tags are fetched again rather than durably stored. Legacy name-only favorites may remain until you remove them."],
  ["6. AI chat and voice data", "A chat request can include the newest prompt, up to 12 recent messages, a compact summary for a saved conversation, referenced Place IDs, confirmed restaurant candidates, official-menu evidence, and—only when personalization is enabled—your selected preferences, allergy or dietary entries, and saved Place IDs. OpenAI processes these inputs to interpret constraints and assess evidence. Location coordinates and map bounds go to CraveAI and Google for search; CraveAI does not intentionally include those coordinates in the OpenAI prompt unless you wrote them in a message. Voice clips are sent through the backend to OpenAI's whisper-1 transcription service."],
  ["7. Temporary and saved conversations", "When History is off, messages and drafts are kept in page memory and browser sessionStorage for temporary tab recovery and are not written as conversations to the CraveAI database. New Chat, logout, or explicit clearing removes that recovery copy; browsers may also clear it when the tab session ends, although browser session-restore behavior can vary. If you enable History or explicitly save a conversation, CraveAI stores your messages, assistant narrative, a generated or edited title, a compact context summary, and referenced Place IDs until you delete them."],
  ["8. Preferences, allergies, saved places, and feedback", "Signed-in users may store optional preferences, including dietary restrictions and allergies. These entries are treated as user-provided sensitive preferences and are used only when personalization is enabled or a request explicitly calls for them; they never establish allergen safety. Saved places store Place IDs and user-authored notes or collection names. Recommendation feedback stores the signed recommendation reference, Place ID, rank, score, confidence, like/dislike choice, optional note, and any report reason. Feedback supports aggregate quality review, not automatic runtime personalization."],
  ["9. Technical information, cookies, and browser storage", "CraveAI uses essential first-party HttpOnly cookies for signed-in sessions, a pseudonymous guest quota token, and short-lived authentication or password-recovery transactions. The guest cookie can last up to 180 days; account sessions cannot be used beyond 30 days and use a 7-day idle limit. Google Maps may store or access information under Google's own policies. localStorage keeps the theme, sidebar preference, and a display copy of current chat-quota status. sessionStorage keeps the guest 18+ acknowledgment and temporary chat recovery. CraveAI has not added an analytics or advertising SDK and does not use non-essential analytics cookies."],
  ["10. Logs, IP, and device information", "The application records request ID, method, path without query parameters, response status, duration, and limited security-event types. It does not intentionally log prompts, message bodies, voice, allergy entries, or provider response bodies. For abuse prevention and quotas, CraveAI stores a keyed hash derived from a network-address prefix rather than the raw IP address; account sessions also store hashes of that prefix and the browser user-agent string. Vercel, Render, Supabase, Google, OpenAI, Open-Meteo, and network providers may independently receive IP address, request, device, and operational log data under their policies."],
  ["11. How information is used", "CraveAI uses information to create and secure accounts; confirm legal eligibility and policy versions; provide maps, weather, restaurant discovery, AI recommendations, and voice transcription; remember choices you intentionally save; operate optional personalization and History; enforce usage limits; investigate errors or abuse; receive feedback; respond to access, correction, export, and deletion requests; comply with law; and maintain the service. Required prompt constraints and explicit exclusions outrank saved preferences."],
  ["12. OpenAI data controls", "CraveAI sets store=false on its OpenAI chat-completion calls and does not create OpenAI application-state records for those calls. The repository cannot verify the operator's optional OpenAI account-level data-sharing setting, so this Policy does not promise that such an optional setting is disabled. OpenAI's published default API policy says API data is not used to train models unless the customer opts in, and default abuse-monitoring logs may be kept for up to 30 days, subject to legal exceptions. OpenAI controls its own provider retention."],
  ["13. Service providers and data sharing", "CraveAI discloses data only as needed to operate the service: Supabase for authentication and PostgreSQL application storage; OpenAI for chat interpretation, evidence assessment, and voice transcription; Google Maps, Places, Geocoding, Autocomplete, photos, and optional Google sign-in; Open-Meteo for weather at the active coordinates; Render for API hosting and server logs; Vercel for frontend hosting and API proxying; and a bounded set of official restaurant websites for public menu evidence. Those websites receive a server request but are not intentionally sent the user's identity, prompt, or saved profile. CraveAI may also disclose information where legally required or necessary to protect users, the service, or others."],
  ["14. Sale, advertising, and model improvement", "CraveAI does not sell personal information, share it for cross-context behavioural advertising, or use it to serve targeted advertisements. CraveAI does not use recommendation feedback for automatic personalization. Whether OpenAI receives API data through an optional provider data-sharing setting cannot be established from this repository; its default and optional uses are described in the preceding section."],
  ["15. Retention", "Account profile data, policy acceptances, current consents, preferences, collections, saved Place IDs, and opted-in conversations remain until you delete or reset them or delete the account. Feedback is removed after up to 24 months or on account deletion. Quota rows are removed after up to 35 days; abuse-event hashes after up to 30 days; application security-audit events after up to 90 days. Authentication transactions expire within 10 minutes and consumed records are cleaned after one day. Sessions expire after 7 idle days or 30 total days; expired session records and revoked records older than 30 days are cleaned by the application. Voice bytes are cleared from CraveAI memory after transcription. Hosting and external providers apply their own retention periods."],
  ["16. Security", "CraveAI uses HTTPS in production, Secure and HttpOnly cookies, SameSite controls, CSRF validation for authenticated mutations, ownership checks, input and upload limits, rate limits, restrictive browser security headers, encrypted Supabase access and refresh tokens in the application database, hashed session and network identifiers, and restricted server-side secrets. The public Google Maps browser key is intentionally exposed to the browser and must be website-referrer and API restricted; the backend Google and OpenAI keys are not sent to the browser. No method of storage or transmission is perfectly secure."],
  ["17. Your choices and controls", "You can deny or revoke browser location permission, choose a manual or fallback area, clear browser storage, remove saved places or notes, disable History or personalization, clear History, reset personalization, export account-owned data, and delete your account. Disabling History stops automatic future saving but does not delete conversations already saved; use Clear History or delete individual conversations. Account deletion requires a recently authenticated session and deletes the Supabase authentication user and account-owned CraveAI database rows. It does not control copies already handled under an external provider's retention policy."],
  ["18. Access, correction, deletion, and Canadian rights", "Subject to applicable law, you may ask what personal information CraveAI holds, how it has been used and disclosed, and request access or correction. Settings provides a machine-readable account export and account deletion; you can also contact the privacy email for help, identity verification, a correction the interface does not support, or a complaint. Canadian privacy law may provide rights of access, correction, and challenge to compliance. You may complain to the Office of the Privacy Commissioner of Canada or another applicable regulator. Other jurisdictions may provide additional deletion, portability, objection, restriction, or consent-withdrawal rights."],
  ["19. International processing", "CraveAI is operated from Ontario, Canada, but the confirmed providers may process information in the United States, Canada, and other countries where they or their subprocessors operate. Information in another country may be accessible to courts, law enforcement, and authorities under that country's laws. Exact provider regions and transfers depend on the operator's provider account configuration and current provider subprocessors."],
  ["20. Children", "CraveAI is an 18+ service and is not directed to children. CraveAI does not knowingly permit a person under 18 to use AI chat, voice, or create an account. Contact the privacy email if you believe a minor provided personal information so the operator can investigate and delete it where appropriate."],
  ["21. Changes and contact", "The version and effective date appear at the top. Material changes require a new acknowledgment from signed-in users before protected features continue. The operator may also provide an in-product notice. Send privacy questions, rights requests, or complaints to the privacy contact below."],
] as const;

export function LegalPage({ kind }: { kind: "terms" | "privacy" }): JSX.Element {
  const [current, setCurrent] = useState<LegalCurrent | null>(null);
  useEffect(() => {
    void fetchLegalCurrent().then(setCurrent).catch(() => undefined);
  }, []);

  const isTerms = kind === "terms";
  const document = isTerms ? current?.terms : current?.privacy;
  const contactEmail =
    (isTerms ? current?.support_email : current?.privacy_email) ||
    (isTerms ? LEGAL_CONFIG.supportEmail : LEGAL_CONFIG.privacyEmail);
  const revisions = current?.revision_history || LEGAL_REVISION_FALLBACK;
  const operatorName = current?.operator_legal_name || LEGAL_CONFIG.operatorName;
  const operatorAddress = current?.operator_address || LEGAL_CONFIG.operatorAddress;
  const governingLaw = current?.governing_law || LEGAL_CONFIG.governingLaw;

  return (
    <article className="product-page legal-page">
      <header className="product-page-heading">
        <p>Legal</p>
        <h1>{isTerms ? "Terms of Service" : "Privacy Policy"}</h1>
        <span>
          Version {document?.version || (isTerms ? LEGAL_CONFIG.termsVersion : LEGAL_CONFIG.privacyVersion)} · Effective {document?.effective_date || LEGAL_CONFIG.effectiveDateLabel}
        </span>
      </header>

      {current && !current.publication_ready ? (
        <div className="legal-review-banner" role="note">
          Legal publication is blocked by unresolved configuration: {(current.publication_issues || []).join(", ") || "review the server configuration"}.
        </div>
      ) : null}

      <p className="legal-intro">
        {isTerms
          ? "These Terms govern access to CraveAI's restaurant discovery, map, chat, voice, saved-place, and account features."
          : "This Policy explains how CraveAI handles information across guest browsing, AI chat, accounts, saved places, optional History, preferences, voice, and feedback."}
      </p>

      <nav aria-label="Legal documents" className="legal-cross-links">
        <a aria-current={isTerms ? "page" : undefined} href="/terms">Terms of Service</a>
        <a aria-current={!isTerms ? "page" : undefined} href="/privacy">Privacy Policy</a>
        <a href="/help/data-use">How CraveAI uses your data</a>
      </nav>

      <div className="legal-sections">
        {(isTerms ? termsSections(operatorName) : privacySections(operatorName)).map(([title, copy]) => (
          <section key={title}><h2>{title}</h2><p>{copy}</p></section>
        ))}
      </div>

      {isTerms ? (
        <section className="legal-sources">
          <h2>Google Maps terms</h2>
          <p>
            CraveAI includes Google Maps features and content. Your use of those features and content is subject to the then-current <a href="https://maps.google.com/help/terms_maps/" rel="noreferrer" target="_blank">Google Maps/Google Earth Additional Terms of Service</a> and <a href="https://policies.google.com/privacy" rel="noreferrer" target="_blank">Google Privacy Policy</a>.
          </p>
        </section>
      ) : (
        <section className="legal-sources">
          <h2>Rights and provider references</h2>
          <p>
            Learn more from the <a href="https://www.priv.gc.ca/en/privacy-topics/privacy-laws-in-canada/the-personal-information-protection-and-electronic-documents-act-pipeda/p_principle/principles/p_access/" rel="noreferrer" target="_blank">Office of the Privacy Commissioner of Canada</a>, <a href="https://platform.openai.com/docs/models/default-usage-policies-by-endpoint" rel="noreferrer" target="_blank">OpenAI API data controls</a>, <a href="https://developers.google.com/maps/documentation/places/web-service/policies" rel="noreferrer" target="_blank">Google Places policies</a>, <a href="https://policies.google.com/privacy" rel="noreferrer" target="_blank">Google Privacy Policy</a>, <a href="https://open-meteo.com/en/terms" rel="noreferrer" target="_blank">Open-Meteo Terms and Privacy</a>, <a href="https://supabase.com/privacy" rel="noreferrer" target="_blank">Supabase Privacy Policy</a>, <a href="https://vercel.com/legal/privacy-notice" rel="noreferrer" target="_blank">Vercel Privacy Notice</a>, and <a href="https://render.com/privacy" rel="noreferrer" target="_blank">Render Privacy Policy</a>.
          </p>
        </section>
      )}

      <footer className="legal-contact">
        <div>
          <strong>Operator and contact</strong>
          <span>{operatorName}</span>
          <address>{operatorAddress}</address>
          <span>{governingLaw}</span>
        </div>
        <a href={`mailto:${contactEmail}`}>{contactEmail}</a>
        <a href="/help/data-use">Read how CraveAI uses your data</a>
      </footer>

      <section className="legal-revisions">
        <h2>Revision history</h2>
        {revisions.map((revision) => (
          <p key={`${revision.terms_version}-${revision.privacy_version}`}>
            <strong>{revision.effective_date}</strong> · {revision.summary} (Terms {revision.terms_version}, Privacy {revision.privacy_version})
          </p>
        ))}
      </section>
    </article>
  );
}
