/* eslint-disable */
/**
 * Generated `api` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type * as aiResearch from "../aiResearch.js";
import type * as auth from "../auth.js";
import type * as dataSources from "../dataSources.js";
import type * as http from "../http.js";
import type * as marketData from "../marketData.js";
import type * as seed from "../seed.js";
import type * as stocks from "../stocks.js";

import type {
  ApiFromModules,
  FilterApi,
  FunctionReference,
} from "convex/server";

declare const fullApi: ApiFromModules<{
  aiResearch: typeof aiResearch;
  auth: typeof auth;
  dataSources: typeof dataSources;
  http: typeof http;
  marketData: typeof marketData;
  seed: typeof seed;
  stocks: typeof stocks;
}>;

/**
 * A utility for referencing Convex functions in your app's public API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = api.myModule.myFunction;
 * ```
 */
export declare const api: FilterApi<
  typeof fullApi,
  FunctionReference<any, "public">
>;

/**
 * A utility for referencing Convex functions in your app's internal API.
 *
 * Usage:
 * ```js
 * const myFunctionReference = internal.myModule.myFunction;
 * ```
 */
export declare const internal: FilterApi<
  typeof fullApi,
  FunctionReference<any, "internal">
>;

export declare const components: {};
