import { describe, expect, it } from "vitest";
import { splitHeading, titleCase } from "./headingCase";

describe("titleCase", () => {
  it("recases a heading the manual printed in capitals", () => {
    expect(titleCase("RAPID/EXPLOSIVE DECOMPRESSION")).toBe("Rapid/Explosive Decompression");
    expect(titleCase("ADVERSE CONDITIONS (FACTORS AFFECTING EVACUATION)")).toBe(
      "Adverse Conditions (Factors Affecting Evacuation)",
    );
  });

  it("keeps small words small, except where a title or bracket opens", () => {
    expect(titleCase("PREPARATION FOR EVACUATION")).toBe("Preparation for Evacuation");
    expect(titleCase("THE ROLE OF THE PURSER")).toBe("The Role of the Purser");
    expect(titleCase("PASSENGERS REQUIRING A PORTABLE OXYGEN")).toBe("Passengers Requiring a Portable Oxygen");
  });

  it("keeps abbreviations, codes, numerals and mixed case as printed", () => {
    expect(titleCase("AIM OF SMS AT IndiGo")).toBe("Aim of SMS at IndiGo"); // pdf 147
    expect(titleCase("SECTION 5 SERIES X PART I ISSUE II (USE OF MOBILE PHONES)")).toBe(
      "Section 5 Series X Part I Issue II (Use of Mobile Phones)",
    );
    expect(titleCase("DOORS ON A320NEO AND A321")).toBe("Doors on A320NEO and A321");
    expect(titleCase("AIRCRAFT RULE 24 A")).toBe("Aircraft Rule 24 A");
    expect(titleCase("CABIN CREW SOPS")).toBe("Cabin Crew SOPs");
    expect(titleCase("DGCA INSPECTORS")).toBe("DGCA Inspectors");
    expect(titleCase("ELECTRONIC NICOTINE DELIVERY SYSTEMS (ENDS) ON BOARD")).toBe(
      "Electronic Nicotine Delivery Systems (ENDS) on Board",
    );
  });

  it("leaves text that is not in capitals alone, beyond tidying its spaces", () => {
    expect(titleCase("Procedure for handling   unruly passengers")).toBe("Procedure for handling unruly passengers");
  });
});

describe("splitHeading", () => {
  it("hangs the number apart from the title", () => {
    expect(splitHeading("1.6    3 POINT BRIEFING")).toEqual({ number: "1.6", title: "3 Point Briefing" });
    expect(splitHeading("2. CREW RESPONSIBILTIES")).toEqual({ number: "2", title: "Crew Responsibilties" });
    expect(splitHeading("GENERAL")).toEqual({ number: null, title: "General" });
  });
});
