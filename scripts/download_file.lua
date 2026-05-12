--[[
  download_file.lua
  -----------------
  Downloads a file from FILE_URL and saves it to DEST_PATH inside the repo.
  Called by the GitHub Actions workflow; reads configuration from environment variables.

  Environment variables (set by the workflow):
    FILE_URL   – direct download URL (required)
    DEST_PATH  – relative destination path inside the repo (optional)
                 If empty, the filename is inferred from the URL and the file
                 is placed in an "uploads/" directory at the repo root.
--]]

-- ── Helpers ──────────────────────────────────────────────────────────────────

--- Exit with an error message.
local function die(msg)
  io.stderr:write("[ERROR] " .. msg .. "\n")
  os.exit(1)
end

--- Extract the filename from a URL (last path segment, query string stripped).
local function filename_from_url(url)
  local name = url:match("/([^/?#]+)%??")
  if not name or name == "" then
    name = "downloaded_file"
  end
  return name
end

--- Extract the directory portion of a path.
local function dirname(path)
  return path:match("^(.*)/[^/]+$")  -- nil if no slash (file is in current dir)
end

--- Create directories recursively, delegating quoting to bash.
local function mkdir_p(dir)
  if not dir or dir == "" then return end
  -- Pass dir as a positional argument so bash handles quoting safely
  local ok = os.execute("bash -c 'mkdir -p \"$1\"' -- " .. string.format("%q", dir))
  if ok ~= 0 then
    die("Could not create directory: " .. dir)
  end
end

-- ── Main ─────────────────────────────────────────────────────────────────────

local file_url  = os.getenv("FILE_URL")
local dest_path = os.getenv("DEST_PATH") or ""

-- Validate input
if not file_url or file_url == "" then
  die("FILE_URL environment variable is not set.")
end

-- Derive destination path when the user left it blank
if dest_path == "" then
  dest_path = "uploads/" .. filename_from_url(file_url)
end

print("[INFO] Source URL  : " .. file_url)
print("[INFO] Destination : " .. dest_path)

-- Create parent directories if needed
local dir = dirname(dest_path)
if dir then
  print("[INFO] Creating directory: " .. dir)
  mkdir_p(dir)
end

-- Download via curl, passing both paths as positional bash args to avoid quoting issues
--   -L  : follow redirects
--   -f  : fail on HTTP errors (exit 22)
--   -sS : silent but show errors
--   -o  : output file
local curl_cmd = string.format(
  "bash -c 'curl -L -f -sS -o \"$1\" \"$2\"' -- %s %s",
  string.format("%q", dest_path),
  string.format("%q", file_url)
)

print("[INFO] Downloading...")
local exit_code = os.execute(curl_cmd)

if exit_code ~= 0 then
  die("curl failed (exit " .. tostring(exit_code) .. "). "
      .. "Check that FILE_URL is a valid, publicly accessible direct-download link.")
end

-- Sanity check – make sure the file is not empty
local f = io.open(dest_path, "rb")
if not f then
  die("Downloaded file not found at: " .. dest_path)
end
local size = f:seek("end")
f:close()

if size == 0 then
  die("Downloaded file is empty. The URL may not point to a real file.")
end

print(string.format("[OK] File saved to '%s' (%d bytes).", dest_path, size))