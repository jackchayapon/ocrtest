import {test,expect} from "@playwright/test";
import {describeCharacters} from "../lib/character-description";

test("Thai vowels, tone marks, quotes and invisible characters have readable names",()=>{
 expect(describeCharacters("ุ")).toContain("สระอุ");
 expect(describeCharacters("่")).toContain("ไม้เอก");
 expect(describeCharacters('"')).toContain("ฟันหนู");
 expect(describeCharacters(" ")).toContain("เว้นวรรค");
 expect(describeCharacters("\u200b")).toContain("ศูนย์ความกว้าง");
 expect(describeCharacters("X")).toBe("X");
 expect(describeCharacters("a!a!").match(/อัศเจรีย์/g)).toHaveLength(1);
 expect(describeCharacters("§")).toContain("U+00A7");
});
