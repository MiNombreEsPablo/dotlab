import test from "node:test";
import assert from "node:assert/strict";
import { friendlyName } from "../image.js";

test("a stored picture is shown by the name it was chosen with", () => {
  assert.equal(friendlyName("/tmp/dotlab/images/e521f5b01373dc57-holiday photo.jpg"), "holiday photo.jpg");
  assert.equal(friendlyName("/tmp/dotlab/compositions/a1b2c3d4e5f6-a1b2c3d4e5f60718-trip.webp"), "trip.webp");
});

test("a picture that never had a name (a paste) is just a picture", () => {
  assert.equal(friendlyName("/tmp/dotlab/images/e521f5b01373dc57.png"), "Picture");
  assert.equal(friendlyName("/tmp/dotlab/compositions/e521f5b01373-e521f5b01373dc57.png"), "Picture");
});

test("names that merely look hexadecimal are left alone", () => {
  assert.equal(friendlyName("/pics/cafe.png"), "cafe.png");
  assert.equal(friendlyName("/pics/deadbeef-holiday.png"), "deadbeef-holiday.png"); // only the engine's 12/16-digit prefixes go
});
