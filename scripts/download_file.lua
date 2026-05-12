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

--- Run a shell command and return trimmed stdout.
local function shell(cmd)
  local handle = io.popen(cmd)
  local result = handle:read("*a")
  handle:close()
  return result:match("^%s*(.-)%s*$")  -- trim whitespace
end

--- Exit with an error message.
local function die(msg)
  io.stderr:write("[ERROR] " .. msg .. "\n")
  os.exit(1)
end

--- Extract the filename from a URL (last path segment, query string stripped).
local function filename_from_url(url)
  local name = url:match("/([^/?#]+)[^/]*$")
  if not name or name == "" then
    name = "downloaded_file"
  end
  return name
end

--- Ensure every directory in the given path exists.
local function mkdir_p(path)
  -- Strip the filename to get the directory portion
  local dir = path:match("^(.*)/[^/]+$")
  if dir and dir ~= "" then
    local code = os.execute("mkdir -p " .. shell("printf '%q' " .. dir))
    if code ~= 0 then
      die("Could not create directory: " .. dir)
    end
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

-- Create parent directories
mkdir_p(dest_path)

-- Download the file with curl
--   -L  : follow redirects
--   -f  : fail silently on HTTP errors (exit code 22)
--   -sS : silent but show errors
--   -o  : output file
local curl_cmd = string.format(
  'curl -L -f -sS -o %s %s',
  shell("printf '%q' " .. dest_path),
  shell("printf '%q' " .. file_url)
)

print("[INFO] Running: " .. curl_cmd)
local exit_code = os.execute(curl_cmd)

if exit_code ~= 0 then
  die("curl failed (exit " .. tostring(exit_code) .. "). "
      .. "Check that FILE_URL is a valid, publicly accessible direct-download link.")
end

-- Quick sanity check – make sure the file is not empty
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